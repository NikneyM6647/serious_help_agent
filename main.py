import sys
import os
from datetime import datetime
from pathlib import Path

import markdown2
from pygments.formatters import HtmlFormatter
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QSettings
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QTextEdit, QComboBox,
    QMessageBox, QSplitter, QFileDialog, QSpinBox, QDialog,
    QDialogButtonBox
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtGui import QShortcut, QKeySequence

from groq import Groq


SYSTEM_DEFAULT = (
    "Ты senior-разработчик. Отвечай кратко, по делу, с примерами кода. "
    "Оформляй код в блоки ```язык ... ```. "
    "Если видишь ошибку — объясни причину и покажи исправление. "
    "Не используй лишние вступления и извинения. Пиши на русском."
)

# CSS для подсветки кода (тема monokai)
PYGMENTS_CSS = HtmlFormatter(style="monokai").get_style_defs(".codehilite")

# extras для markdown2 с подсветкой кода
MD_EXTRAS = {
    "tables": None,
    "fenced-code-blocks": None,
    "strike": None,
    "task_list": None,
    "code-color": {"style": "monokai"},
}


# ======================= WORKERS =======================
class GroqWorker(QThread):
    chunk = Signal(str)
    done = Signal()
    error = Signal(str)

    def __init__(self, api_key, model, messages, temperature=0.7):
        super().__init__()
        self.api_key = api_key
        self.model = model
        self.messages = messages
        self.temperature = temperature

    def run(self):
        try:
            client = Groq(api_key=self.api_key)
            stream = client.chat.completions.create(
                model=self.model,
                messages=self.messages,
                temperature=self.temperature,
                stream=True,
            )
            for part in stream:
                delta = part.choices[0].delta.content
                if delta:
                    self.chunk.emit(delta)
            self.done.emit()
        except Exception as e:
            self.error.emit(str(e))


class ModelsWorker(QThread):
    done = Signal(list)
    error = Signal(str)

    def __init__(self, api_key):
        super().__init__()
        self.api_key = api_key

    def run(self):
        try:
            client = Groq(api_key=self.api_key)
            ids = [m.id for m in client.models.list().data]
            chat = [m for m in ids if not any(
                x in m.lower() for x in ("whisper", "tts", "guard", "prompt-guard")
            )]
            self.done.emit(sorted(chat))
        except Exception as e:
            self.error.emit(str(e))


# ======================= ДИАЛОГ ВЫБОРА ОТВЕТА =======================
class AnswerPickerDialog(QDialog):
    """Окно выбора номера ответа для сохранения."""

    def __init__(self, qa_pairs, default_n, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Какой ответ сохранять?")
        self.setMinimumWidth(420)
        self.qa_pairs = qa_pairs
        self._result_n = default_n

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        total = len(qa_pairs)
        layout.addWidget(QLabel(f"Всего ответов: {total}"))

        row = QHBoxLayout()
        row.addWidget(QLabel("Номер ответа:"))
        self.spin = QSpinBox()
        self.spin.setRange(1, total)
        self.spin.setValue(default_n if 1 <= default_n <= total else total)
        self.spin.setFixedWidth(80)
        self.spin.valueChanged.connect(self._update_preview)
        row.addWidget(self.spin)
        row.addStretch()
        layout.addLayout(row)

        layout.addWidget(QLabel("Вопрос (первые 50 символов):"))
        self.preview = QLineEdit()
        self.preview.setReadOnly(True)
        layout.addWidget(self.preview)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

        self.setStyleSheet("""
            QDialog { background:#1e1f24; color:#e6e6e6; }
            QLabel { color:#e6e6e6; }
            QSpinBox, QLineEdit {
                background:#2a2c33; border:1px solid #3a3d47;
                border-radius:6px; padding:6px; color:#e6e6e6;
            }
            QSpinBox:focus, QLineEdit:focus { border:1px solid #7aa2f7; }
            QPushButton {
                background:#2a2c33; border:1px solid #3a3d47;
                border-radius:6px; padding:6px 16px; color:#e6e6e6;
                min-width:70px;
            }
            QPushButton:hover { background:#333640; }
        """)

        self._update_preview()

    def _update_preview(self):
        n = self.spin.value()
        if 1 <= n <= len(self.qa_pairs):
            q = self.qa_pairs[n - 1]["question"].replace("\n", " ")
            self.preview.setText(q[:50] + ("…" if len(q) > 50 else ""))
        else:
            self.preview.clear()

    def selected_number(self) -> int:
        return self.spin.value()


# ======================= MAIN WINDOW =======================
class GroqChat(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Groq Chat — Markdown")
        self.resize(1150, 900)

        self.settings = QSettings("groq_chat", "app")
        self.api_key = ""
        self.last_dir = self.settings.value("last_dir", str(Path.home()))
        self.history = []
        self.worker = None
        self.models_worker = None

        self._md_full = ""
        self._md_current = ""
        self._last_response = ""
        self._last_user = ""

        self.qa_pairs = []
        self._view_mode = "all"

        self._render_timer = QTimer()
        self._render_timer.setSingleShot(True)
        self._render_timer.setInterval(150)
        self._render_timer.timeout.connect(self._render_markdown)

        self._build_ui()
        self._apply_style()

        QShortcut(QKeySequence("Ctrl+Return"), self, activated=self.send_message)
        QShortcut(QKeySequence("Ctrl+Enter"), self, activated=self.send_message)

        self._load_settings()

    # ---------------- UI ----------------
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # --- API key ---
        key_row = QHBoxLayout()
        key_row.addWidget(QLabel("Groq API-key:"))
        self.key_edit = QLineEdit()
        self.key_edit.setPlaceholderText("gsk_...")
        self.key_edit.setEchoMode(QLineEdit.Password)
        key_row.addWidget(self.key_edit, 1)

        self.show_key_btn = QPushButton("👁")
        self.show_key_btn.setFixedWidth(36)
        self.show_key_btn.clicked.connect(self._toggle_key)
        key_row.addWidget(self.show_key_btn)

        self.save_key_btn = QPushButton("Сохранить ключ")
        self.save_key_btn.clicked.connect(self._save_key)
        key_row.addWidget(self.save_key_btn)
        root.addLayout(key_row)

        # --- models ---
        mid = QHBoxLayout()
        mid.addWidget(QLabel("Модель:"))
        self.model_combo = QComboBox()
        self.model_combo.addItems([
            "openai/gpt-oss-120b",
            "openai/gpt-oss-20b",
            "qwen/qwen3-32b",
            "llama-3.1-8b-instant",
        ])
        self.model_combo.setEditable(True)
        mid.addWidget(self.model_combo, 1)

        self.refresh_btn = QPushButton("🔄 Обновить модели")
        self.refresh_btn.clicked.connect(self.refresh_models)
        mid.addWidget(self.refresh_btn)
        root.addLayout(mid)

        # --- панель навигации по ответам ---
        nav = QHBoxLayout()
        nav.addWidget(QLabel("Ответ №:"))

        self.answer_spin = QSpinBox()
        self.answer_spin.setRange(0, 0)
        self.answer_spin.setSpecialValueText("—")
        self.answer_spin.setFixedWidth(70)
        self.answer_spin.valueChanged.connect(self._on_answer_number_changed)
        nav.addWidget(self.answer_spin)

        self.counter_label = QLabel("из 0")
        self.counter_label.setStyleSheet("color:#888;")
        nav.addWidget(self.counter_label)

        nav.addSpacing(8)
        nav.addWidget(QLabel("Вопрос:"))
        self.preview_edit = QLineEdit()
        self.preview_edit.setReadOnly(True)
        self.preview_edit.setPlaceholderText("(тут покажется начало вопроса)")
        nav.addWidget(self.preview_edit, 1)

        self.goto_btn = QPushButton("↩ Перейти")
        self.goto_btn.setToolTip("Показать только этот ответ")
        self.goto_btn.clicked.connect(self._goto_selected_answer)
        nav.addWidget(self.goto_btn)

        self.show_all_btn = QPushButton("📜 Показать весь чат")
        self.show_all_btn.clicked.connect(self._show_all_chat)
        nav.addWidget(self.show_all_btn)

        root.addLayout(nav)

        # --- системный промпт ---
        root.addWidget(QLabel("Системный промпт:"))
        self.sys_edit = QTextEdit()
        self.sys_edit.setFixedHeight(70)
        self.sys_edit.setPlainText(SYSTEM_DEFAULT)
        root.addWidget(self.sys_edit)

        # --- splitter ---
        splitter = QSplitter(Qt.Vertical)

        self.output = QWebEngineView()
        self.output.setHtml(self._wrap_html(""))
        splitter.addWidget(self.output)

        input_widget = QWidget()
        input_l = QVBoxLayout(input_widget)
        input_l.setContentsMargins(0, 6, 0, 0)
        input_l.setSpacing(6)

        input_l.addWidget(QLabel("Запрос (Ctrl+Enter — отправить, Enter — новая строка):"))
        self.input_edit = QTextEdit()
        self.input_edit.setPlaceholderText(
            "Введи запрос или вставь код. Ctrl+Enter — отправить."
        )
        self.input_edit.setFixedHeight(120)
        input_l.addWidget(self.input_edit)

        row1 = QHBoxLayout()
        self.send_btn = QPushButton("▶  Отправить (Ctrl+Enter)")
        self.send_btn.setObjectName("sendBtn")
        self.send_btn.setMinimumHeight(40)
        self.send_btn.clicked.connect(self.send_message)
        row1.addWidget(self.send_btn, 2)

        self.clear_btn = QPushButton("🗑 Очистить чат")
        self.clear_btn.clicked.connect(self.clear_chat)
        row1.addWidget(self.clear_btn)

        self.clear_input_btn = QPushButton("🧹 Очистить ввод")
        self.clear_input_btn.clicked.connect(lambda: self.input_edit.clear())
        row1.addWidget(self.clear_input_btn)
        input_l.addLayout(row1)

        row2 = QHBoxLayout()
        self.copy_btn = QPushButton("📋 Копировать ответ")
        self.copy_btn.setToolTip("Скопировать последний (или выбранный) ответ")
        self.copy_btn.clicked.connect(self._copy_md)
        row2.addWidget(self.copy_btn)

        self.save_btn = QPushButton("💾 Сохранить ответ как…")
        self.save_btn.setToolTip("Выбрать номер ответа → имя, папку и формат")
        self.save_btn.clicked.connect(self._save_md)
        row2.addWidget(self.save_btn)

        self.save_folder_btn = QPushButton("📁 Ответ в папку…")
        self.save_folder_btn.setToolTip("Выбрать номер ответа → папку")
        self.save_folder_btn.clicked.connect(self._save_to_folder)
        row2.addWidget(self.save_folder_btn)

        self.open_folder_btn = QPushButton("📂 Открыть папку")
        self.open_folder_btn.clicked.connect(
            lambda: self._open_folder(self.last_dir)
        )
        row2.addWidget(self.open_folder_btn)

        input_l.addLayout(row2)

        splitter.addWidget(input_widget)
        splitter.setSizes([600, 260])
        root.addWidget(splitter, 1)

        self.status = QLabel("Готов к работе")
        self.status.setStyleSheet("color:#888;")
        root.addWidget(self.status)

    def _apply_style(self):
        self.setStyleSheet("""
            QMainWindow, QWidget { background:#1e1f24; color:#e6e6e6; }
            QLineEdit, QTextEdit, QComboBox, QSpinBox {
                background:#2a2c33; border:1px solid #3a3d47;
                border-radius:6px; padding:6px; color:#e6e6e6;
            }
            QLineEdit:focus, QTextEdit:focus, QSpinBox:focus {
                border:1px solid #7aa2f7;
            }
            QLineEdit[readOnly="true"] { color:#b0b0b0; }
            QPushButton {
                background:#2a2c33; border:1px solid #3a3d47;
                border-radius:6px; padding:7px 12px; color:#e6e6e6;
            }
            QPushButton:hover { background:#333640; }
            QPushButton#sendBtn {
                background:#7aa2f7; color:#1e1f24;
                font-weight:bold; font-size:14px; border:none;
            }
            QPushButton#sendBtn:hover { background:#8fb3ff; }
            QPushButton#sendBtn:disabled { background:#4a5568; color:#999; }
            QSplitter::handle { background:#2a2c33; }
        """)

    # ---------------- HTML ----------------
    def _wrap_html(self, body: str) -> str:
        return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
  body {{
    background:#1e1f24; color:#e6e6e6;
    font-family:-apple-system,'Segoe UI',Roboto,sans-serif;
    font-size:15px; line-height:1.6;
    padding:16px 22px; margin:0;
  }}
  h1,h2,h3,h4 {{ color:#7aa2f7; margin-top:1.2em; margin-bottom:.5em; }}
  h1 {{ font-size:1.7em; border-bottom:1px solid #3a3d47; padding-bottom:.3em; }}
  h2 {{ font-size:1.4em; border-bottom:1px solid #2a2c33; padding-bottom:.2em; }}
  h3 {{ font-size:1.15em; }}
  a {{ color:#7aa2f7; }}
  code {{
    background:#2a2c33; padding:2px 6px; border-radius:4px;
    font-family:Consolas,monospace; font-size:.92em; color:#ffcc66;
  }}
  pre {{
    background:#2a2c33; padding:12px; border-radius:6px;
    overflow-x:auto; border:1px solid #3a3d47;
  }}
  pre code {{ background:none; padding:0; color:#e6e6e6; }}
  blockquote {{
    border-left:3px solid #7aa2f7; margin:1em 0;
    padding:.3em 1em; color:#b0b0b0; background:#22242a;
  }}
  table {{ border-collapse:collapse; margin:1em 0; width:100%; }}
  th,td {{ border:1px solid #3a3d47; padding:8px 12px; text-align:left; }}
  th {{ background:#2a2c33; color:#7aa2f7; }}
  tr:nth-child(even) td {{ background:#22242a; }}
  ul,ol {{ padding-left:1.6em; }}
  li {{ margin:.25em 0; }}
  hr {{ border:none; border-top:1px solid #3a3d47; margin:1.4em 0; }}
  .user-block {{
    background:#22242a; border-left:3px solid #7aa2f7;
    padding:10px 14px; border-radius:6px; margin:14px 0;
    white-space:pre-wrap; font-family:Consolas,monospace; font-size:.92em;
  }}
  .user-label {{ color:#7aa2f7; font-weight:bold; margin-bottom:4px;
                  font-family:-apple-system,'Segoe UI',sans-serif; }}
  .bot-label  {{ color:#ffcc66; font-weight:bold; margin-top:18px; margin-bottom:6px; }}
  .err {{ color:#ff6b6b; }}
  .badge {{
    display:inline-block; background:#7aa2f7; color:#1e1f24;
    padding:2px 10px; border-radius:12px; font-weight:bold;
    font-size:.85em; margin-bottom:6px;
  }}
  {PYGMENTS_CSS}
</style></head><body>{body}</body></html>"""

    def _render_markdown(self):
        html_body = markdown2.markdown(
            self._md_full + self._md_current,
            extras=MD_EXTRAS,
        )
        self.output.setHtml(self._wrap_html(html_body))
        QTimer.singleShot(60, lambda: self.output.page().runJavaScript(
            "window.scrollTo(0, document.body.scrollHeight);"
        ))

    # ---------------- Настройки ----------------
    def _load_settings(self):
        key = self.settings.value("api_key", "")
        if key:
            self.api_key = key
            self.key_edit.setText(key)
            self.refresh_models()

    def _save_key(self):
        self.api_key = self.key_edit.text().strip()
        self.settings.setValue("api_key", self.api_key)
        self.status.setText("API-ключ сохранён")
        self.refresh_models()

    def _toggle_key(self):
        if self.key_edit.echoMode() == QLineEdit.Password:
            self.key_edit.setEchoMode(QLineEdit.Normal)
        else:
            self.key_edit.setEchoMode(QLineEdit.Password)

    # ---------------- Модели ----------------
    def refresh_models(self):
        if not self.api_key:
            self.api_key = self.key_edit.text().strip()
        if not self.api_key:
            QMessageBox.warning(self, "Нет ключа", "Сначала вставь API-ключ Groq")
            return

        self.refresh_btn.setEnabled(False)
        self.refresh_btn.setText("⏳ Загрузка…")

        self.models_worker = ModelsWorker(self.api_key)
        self.models_worker.done.connect(self._on_models_loaded)
        self.models_worker.error.connect(self._on_models_error)
        self.models_worker.start()

    def _on_models_loaded(self, ids):
        current = self.model_combo.currentText()
        self.model_combo.clear()
        self.model_combo.addItems(ids)
        if current in ids:
            self.model_combo.setCurrentText(current)
        self.refresh_btn.setEnabled(True)
        self.refresh_btn.setText("🔄 Обновить модели")
        self.status.setText(f"Загружено моделей: {len(ids)}")

    def _on_models_error(self, msg):
        self.refresh_btn.setEnabled(True)
        self.refresh_btn.setText("🔄 Обновить модели")
        QMessageBox.critical(self, "Ошибка загрузки моделей", msg)

    # ---------------- Отправка ----------------
    def send_message(self):
        text = self.input_edit.toPlainText().strip()
        if not text:
            return
        if not self.api_key:
            self.api_key = self.key_edit.text().strip()
        if not self.api_key:
            QMessageBox.warning(self, "Нет ключа", "Введи API-ключ Groq")
            return

        model = self.model_combo.currentText().strip()
        if not model:
            QMessageBox.warning(self, "Нет модели", "Нажми 'Обновить модели'")
            return

        self.input_edit.clear()
        self._view_mode = "all"

        self._last_user = text
        self._last_response = ""

        safe_user = text.replace("</", "<\\/")
        n = len(self.qa_pairs) + 1
        block = (
            f'<div class="badge">Ответ №{n}</div>\n'
            f'<div class="user-label">🧑 Вы</div>\n'
            f'<div class="user-block">{safe_user}</div>\n\n'
            f'<div class="bot-label">🤖 Groq</div>\n\n'
        )
        self._md_full += block
        self._md_current = ""
        self._render_markdown()

        sys_prompt = self.sys_edit.toPlainText().strip()
        messages = []
        if sys_prompt:
            messages.append({"role": "system", "content": sys_prompt})
        messages.extend(self.history)
        messages.append({"role": "user", "content": text})

        self.send_btn.setEnabled(False)
        self.send_btn.setText("⏳ Генерация…")
        self.status.setText(f"Запрос к {model}…")

        self.worker = GroqWorker(self.api_key, model, messages)
        self.worker.chunk.connect(self._on_chunk)
        self.worker.done.connect(self._on_done)
        self.worker.error.connect(self._on_error)
        self.worker.start()

    def _on_chunk(self, text):
        self._md_current += text
        if self._view_mode == "all" and not self._render_timer.isActive():
            self._render_timer.start()

    def _on_done(self):
        self._render_timer.stop()

        answer = self._md_current.strip()
        question = self._last_user

        if answer:
            self.history.append({"role": "assistant", "content": answer})
            self._last_response = answer

            n = len(self.qa_pairs) + 1
            safe_user = question.replace("</", "<\\/")
            md_block = (
                f'<div class="badge">Ответ №{n}</div>\n'
                f'<div class="user-label">🧑 Вы</div>\n'
                f'<div class="user-block">{safe_user}</div>\n\n'
                f'<div class="bot-label">🤖 Groq</div>\n\n'
                f'{answer}\n\n<hr>\n\n'
            )

            self.qa_pairs.append({
                "n": n,
                "question": question,
                "answer": answer,
                "md_block": md_block,
            })

            self._md_full = "".join(p["md_block"] for p in self.qa_pairs)
            self._md_current = ""
            self._update_nav_after_new()
        else:
            self._md_current = ""

        self._render_markdown()
        self.send_btn.setEnabled(True)
        self.send_btn.setText("▶  Отправить (Ctrl+Enter)")
        self.status.setText("Готово")

    def _on_error(self, msg):
        self._render_timer.stop()
        self._md_full += f'<div class="err">⚠ Ошибка: {msg}</div>\n\n<hr>\n\n'
        self._md_current = ""
        self._render_markdown()
        self.send_btn.setEnabled(True)
        self.send_btn.setText("▶  Отправить (Ctrl+Enter)")
        self.status.setText("Ошибка")

    # ---------------- Навигация ----------------
    def _update_nav_after_new(self):
        total = len(self.qa_pairs)
        self.answer_spin.blockSignals(True)
        self.answer_spin.setRange(0, total)
        self.answer_spin.setValue(total)
        self.answer_spin.blockSignals(False)

        self.counter_label.setText(f"из {total}")

        if total > 0:
            q = self.qa_pairs[-1]["question"].replace("\n", " ")
            self.preview_edit.setText(q[:50] + ("…" if len(q) > 50 else ""))

    def _on_answer_number_changed(self, value: int):
        if value <= 0 or value > len(self.qa_pairs):
            self.preview_edit.clear()
            return
        q = self.qa_pairs[value - 1]["question"].replace("\n", " ")
        self.preview_edit.setText(q[:50] + ("…" if len(q) > 50 else ""))

    def _goto_selected_answer(self):
        n = self.answer_spin.value()
        if n <= 0 or n > len(self.qa_pairs):
            QMessageBox.information(
                self, "Нет такого ответа",
                "Выбери номер ответа в поле «Ответ №»."
            )
            return

        pair = self.qa_pairs[n - 1]
        self._view_mode = "single"
        html_body = markdown2.markdown(
            pair["md_block"],
            extras=MD_EXTRAS,
        )
        self.output.setHtml(self._wrap_html(html_body))
        self.status.setText(f"Показан ответ №{n}")

    def _show_all_chat(self):
        self._view_mode = "all"
        self._render_markdown()
        self.status.setText("Показан весь чат")

    # ---------------- Утилиты ----------------
    def clear_chat(self):
        self._md_full = ""
        self._md_current = ""
        self._last_response = ""
        self._last_user = ""
        self.history.clear()
        self.qa_pairs.clear()

        self.answer_spin.blockSignals(True)
        self.answer_spin.setRange(0, 0)
        self.answer_spin.setValue(0)
        self.answer_spin.blockSignals(False)
        self.counter_label.setText("из 0")
        self.preview_edit.clear()

        self._view_mode = "all"
        self.output.setHtml(self._wrap_html(""))
        self.status.setText("Чат очищен")

    def _copy_md(self):
        n = self.answer_spin.value()
        text = ""
        if 1 <= n <= len(self.qa_pairs):
            text = self.qa_pairs[n - 1]["answer"]
        else:
            text = self._last_response
        if not text:
            self.status.setText("Нет ответа для копирования")
            return
        QApplication.clipboard().setText(text)
        self.status.setText("Ответ скопирован в буфер")

    # ---------- ВЫБОР НОМЕРА ДЛЯ СОХРАНЕНИЯ ----------
    def _ask_answer_number(self):
        if not self.qa_pairs:
            QMessageBox.information(
                self, "Пусто",
                "Нет ни одного ответа. Сначала сгенерируй ответ."
            )
            return None

        default_n = self.answer_spin.value() or len(self.qa_pairs)
        dlg = AnswerPickerDialog(self.qa_pairs, default_n, self)
        if dlg.exec() != QDialog.Accepted:
            return None
        return dlg.selected_number()

    def _get_answer_by_n(self, n: int) -> str:
        if 1 <= n <= len(self.qa_pairs):
            return self.qa_pairs[n - 1]["answer"]
        return ""

    # ---------- СОХРАНЕНИЕ ----------
    def _save_md(self):
        n = self._ask_answer_number()
        if n is None:
            return

        text = self._get_answer_by_n(n)
        if not text:
            QMessageBox.information(self, "Пусто", "Ответ не найден.")
            return

        default_name = f"answer_{n:03d}_{datetime.now():%Y%m%d_%H%M%S}.md"
        default_path = str(Path(self.last_dir) / default_name)

        path, _ = QFileDialog.getSaveFileName(
            self,
            f"Сохранить ответ №{n}",
            default_path,
            "Markdown (*.md);;HTML (*.html);;Текст (*.txt);;Все файлы (*)",
        )
        if not path:
            return

        try:
            Path(path).write_text(text, encoding="utf-8")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка сохранения", str(e))
            return

        self.last_dir = str(Path(path).parent)
        self.settings.setValue("last_dir", self.last_dir)
        self.status.setText(f"Сохранён ответ №{n}: {path}")

    def _save_to_folder(self):
        n = self._ask_answer_number()
        if n is None:
            return

        text = self._get_answer_by_n(n)
        if not text:
            QMessageBox.information(self, "Пусто", "Ответ не найден.")
            return

        folder = QFileDialog.getExistingDirectory(
            self,
            f"Куда сохранить ответ №{n}",
            self.last_dir,
        )
        if not folder:
            return

        filename = f"answer_{n:03d}_{datetime.now():%Y%m%d_%H%M%S}.md"
        full_path = Path(folder) / filename

        try:
            full_path.write_text(text, encoding="utf-8")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка сохранения", str(e))
            return

        self.last_dir = folder
        self.settings.setValue("last_dir", self.last_dir)

        answer = QMessageBox.question(
            self,
            "Сохранено",
            f"Ответ №{n} сохранён:\n{full_path}\n\nОткрыть папку?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if answer == QMessageBox.Yes:
            self._open_folder(str(full_path.parent))

        self.status.setText(f"Сохранён ответ №{n}: {full_path}")

    def _open_folder(self, path: str):
        import subprocess
        try:
            if sys.platform.startswith("win"):
                os.startfile(path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as e:
            self.status.setText(f"Не удалось открыть папку: {e}")

    def closeEvent(self, e):
        self.settings.setValue("api_key", self.key_edit.text().strip())
        self.settings.setValue("last_dir", self.last_dir)
        if self.worker and self.worker.isRunning():
            self.worker.terminate()
            self.worker.wait(500)
        super().closeEvent(e)


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    w = GroqChat()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()