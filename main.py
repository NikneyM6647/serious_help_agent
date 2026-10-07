import json
import re
import sys
from datetime import datetime
from pathlib import Path

import markdown2
from PySide6.QtCore import Qt, QThread, Signal, QSettings, QTimer
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QPlainTextEdit, QComboBox,
    QSpinBox, QFileDialog, QMessageBox, QSplitter,
    QListWidget, QListWidgetItem,
)
from PySide6.QtWebEngineWidgets import QWebEngineView

from groq import Groq


# ======================= ШАБЛОНЫ ХРОНОЛОГИИ =======================
TEMPLATES = {
    "🎬 Обзор кафе / ресторана": (
        "1. Хук — самый аппетитный/атмосферный кадр\n"
        "2. Вывеска и фасад снаружи\n"
        "3. Заход в зал (POV-проход через дверь)\n"
        "4. Общий план зала — атмосфера, свет, посадка\n"
        "5. Детали интерьера (декор, мебель, музыка)\n"
        "6. Меню — пролистывание, крупные планы блюд и цен\n"
        "7. Заказ — диалог с официантом\n"
        "8. Ожидание — чем занят гость, антураж\n"
        "9. Подача блюда — крупные планы, пар, текстура\n"
        "10. Проба еды — честная реакция\n"
        "11. Атмосфера — люди, музыка, детали вокруг\n"
        "12. Туалет / чистота заведения\n"
        "13. Счёт — сумма чека, цена/качество\n"
        "14. Вердикт — кому зайдёт, оценка по 10-балльной\n"
        "15. Аутро — финальный кадр, призыв"
    ),
    "🏨 Обзор отеля": (
        "1. Хук — самый впечатляющий вид или номер\n"
        "2. Фасад, вход, лобби\n"
        "3. Ресепшн — заселение (POV)\n"
        "4. Коридор до номера\n"
        "5. Номер — общий план\n"
        "6. Кровать, постель, подушки (крупно)\n"
        "7. Ванная — чистота, полотенца, косметика\n"
        "8. Балкон / вид из окна\n"
        "9. Завтрак / ресторан отеля\n"
        "10. Инфраструктура (бассейн, спортзал, spa)\n"
        "11. Сервис — реакции, детали обслуживания\n"
        "12. Ночная атмосфера\n"
        "13. Цена за ночь, соотношение цена/качество\n"
        "14. Вердикт — кому подойдёт, оценка\n"
        "15. Аутро"
    ),
    "📱 Обзор гаджета": (
        "1. Хук — самый вау-момент или неожиданный факт\n"
        "2. Распаковка (unboxing) — коробка, комплект\n"
        "3. Внешний вид — материалы, вес, эргономика\n"
        "4. Экран / дисплей — цвет, яркость, частота\n"
        "5. Железо / характеристики\n"
        "6. Софт — интерфейс, фишки, реклама\n"
        "7. Камера — примеры фото/видео\n"
        "8. Автономность — тест батареи\n"
        "9. Игры / производительность\n"
        "10. Сравнение с конкурентом\n"
        "11. Минусы и разочарования\n"
        "12. Цена и конкуренты\n"
        "13. Вердикт — кому брать, кому нет\n"
        "14. Аутро"
    ),
    "✈️ Влог о поездке": (
        "1. Хук — самый красивый или смешной кадр\n"
        "2. Сборы / аэропорт / дорога\n"
        "3. Прибытие — первое впечатление\n"
        "4. Жильё — быстрый тур\n"
        "5. Первый выход в город\n"
        "6. Еда — местная кухня\n"
        "7. Главная достопримечательность\n"
        "8. Неожиданный/спонтанный момент\n"
        "9. Вечер, огни, атмосфера\n"
        "10. Проблема или фейл в поездке\n"
        "11. Финал поездки, обратная дорога\n"
        "12. Итог — стоимость, впечатления, советы\n"
        "13. Аутро"
    ),
    "🎉 Корпоратив / ивент": (
        "1. Хук — самый яркий момент вечера (танец/тост/награда)\n"
        "2. Подготовка — сборы, дорога\n"
        "3. Приход гостей, фойе, знакомство\n"
        "4. Открытие — приветствие ведущего\n"
        "5. Речь/поздравление руководителя\n"
        "6. Награждение сотрудников\n"
        "7. Застолье — тосты, эмоции, детали блюд\n"
        "8. Конкурсы и активности\n"
        "9. Танцы, DJ, музыка\n"
        "10. Интервью-нарезка с гостями (2–3 фразы)\n"
        "11. Кульминация вечера (салют/сюрприз/общий тост)\n"
        "12. Финальные кадры — объятия, уход\n"
        "13. Аутро — благодарность, логотип компании"
    ),
    "🎮 Обзор игры / фильма": (
        "1. Хук — самая яркая сцена без спойлеров\n"
        "2. Что это и о чём (без спойлеров)\n"
        "3. Автор / студия / контекст\n"
        "4. Первое впечатление\n"
        "5. Геймплей / сюжет (без спойлеров)\n"
        "6. Графика / картинка / звук\n"
        "7. Сильные стороны\n"
        "8. Слабые стороны и баги\n"
        "9. Сравнение с похожими\n"
        "10. Цена / доступность\n"
        "11. Вердикт — кому зайдёт, оценка\n"
        "12. Аутро"
    ),
    "🛠 Своя хронология": (
        "Придумай хронологию сам, исходя из темы. Учти специфику жанра "
        "и предложи оптимальный порядок сцен."
    ),
}


DEFAULT_MODELS = [
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "llama-3.1-8b-instant",
    "meta-llama/llama-4-scout-17b-16e-instruct",
]


SYSTEM = """Ты — опытный сценарист YouTube-видео и коротких форматов
(Shorts/Reels/TikTok). Пишешь живо, конкретно, без воды и клише.
Структурируешь текст: хук, развитие, кульминация, призыв.
Учитываешь тайминг (примерно 2.5 слова в секунду).

Используй markdown для структуры: заголовки (##), списки, таблицы,
жирный текст. Пиши на русском."""


# ======================= ЧИСТКА MARKDOWN =======================
def strip_markdown(text: str) -> str:
    """Убирает markdown-разметку и оставляет чистый текст."""
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</?[a-zA-Z][^>]*>", "", text)

    out = []
    for line in text.split("\n"):
        if re.match(r"^\s*\|?[\s\-:|]+\|?\s*$", line) and "|" in line:
            continue
        line = re.sub(r"^\s*\|\s*", "", line)
        line = re.sub(r"\s*\|\s*$", "", line)
        line = re.sub(r"\s*\|\s*", " — ", line)
        out.append(line)
    text = "\n".join(out)

    text = re.sub(r"```[a-zA-Z0-9]*\n?", "", text)
    text = text.replace("```", "")
    text = re.sub(r"`([^`]+)`", r"\1", text)

    text = re.sub(r"\*{3}(.+?)\*{3}", r"\1", text, flags=re.S)
    text = re.sub(r"\*{2}(.+?)\*{2}", r"\1", text, flags=re.S)
    text = re.sub(r"\*(.+?)\*", r"\1", text, flags=re.S)
    text = re.sub(r"~~(.+?)~~", r"\1", text, flags=re.S)
    text = re.sub(r"(?<!\w)_([^_]+)_(?!\w)", r"\1", text)

    text = re.sub(r"^\s*#{1,6}\s*", "", text, flags=re.M)
    text = re.sub(r"^\s*>\s?", "", text, flags=re.M)

    emoji = re.compile(
        "[\U0001F300-\U0001FAFF\U00002600-\U000027BF"
        "\U0001F1E6-\U0001F1FF\U00002190-\U000021FF\U00002B00-\U00002BFF]+",
        flags=re.UNICODE,
    )
    text = emoji.sub("", text)

    text = re.sub(r"^\s*\*\s+", "- ", text, flags=re.M)
    text = text.replace("*", "")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ======================= WORKER =======================
class Worker(QThread):
    chunk = Signal(str)
    done = Signal()
    error = Signal(str)

    def __init__(self, api_key, model, prompt, temperature=0.7):
        super().__init__()
        self.api_key = api_key
        self.model = model
        self.prompt = prompt
        self.temperature = temperature

    def run(self):
        try:
            client = Groq(api_key=self.api_key)
            stream = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": self.prompt},
                ],
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


# ======================= КНОПКА ЗАДАЧИ =======================
class TaskButton(QPushButton):
    def __init__(self, text, task_id):
        super().__init__(text)
        self.task_id = task_id
        self.setCheckable(True)
        self.setMinimumHeight(38)
        self.setCursor(Qt.PointingHandCursor)


# ======================= ГЛАВНОЕ ОКНО =======================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Помощник сценариста")
        self.resize(1350, 800)

        self.settings = QSettings("script_helper", "app")
        self.worker = None
        self.current_task = None
        self._md_buffer = ""

        self.history_file = Path.home() / ".script_helper_history.json"
        self.history = self._load_history()

        self._render_timer = QTimer()
        self._render_timer.setSingleShot(True)
        self._render_timer.setInterval(180)
        self._render_timer.timeout.connect(self._render_markdown)

        self._build_ui()
        self._apply_style()
        self._load_settings()
        self._select_task("ideas")
        self._refresh_history_view()

    # ---------------- UI ----------------
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

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

        # --- main splitter ---
        splitter = QSplitter(Qt.Horizontal)
        root.addWidget(splitter, 1)

        # ===== ЛЕВАЯ ПАНЕЛЬ =====
        left = QWidget()
        left_l = QVBoxLayout(left)
        left_l.setContentsMargins(0, 0, 6, 0)
        left_l.setSpacing(8)

        left_l.addWidget(self._section("Инструменты"))

        tasks = [
            ("💡 Идеи для видео",       "ideas"),
            ("🎬 План съёмки (хроно)",  "shooting"),
            ("🎣 Хуки (первые 5 сек)",  "hooks"),
            ("📝 Полный сценарий",      "script"),
            ("✨ Улучшить текст",       "improve"),
            ("⏱ Разбить по таймингу",   "timing"),
            ("🏷 Заголовки",            "titles"),
        ]
        self.task_buttons = {}
        for label, tid in tasks:
            btn = TaskButton(label, tid)
            btn.clicked.connect(lambda _=False, t=tid: self._select_task(t))
            left_l.addWidget(btn)
            self.task_buttons[tid] = btn

        left_l.addSpacing(6)

        self.template_label = QLabel("Шаблон хронологии:")
        left_l.addWidget(self.template_label)
        self.template_combo = QComboBox()
        self.template_combo.addItems(list(TEMPLATES.keys()))
        left_l.addWidget(self.template_combo)

        left_l.addSpacing(6)
        left_l.addWidget(self._section("Параметры"))

        left_l.addWidget(QLabel("Модель:"))
        model_row = QHBoxLayout()
        self.model_combo = QComboBox()
        self.model_combo.addItems(DEFAULT_MODELS)
        self.model_combo.setEditable(True)
        model_row.addWidget(self.model_combo, 1)
        self.refresh_btn = QPushButton("🔄")
        self.refresh_btn.setFixedWidth(36)
        self.refresh_btn.setToolTip("Обновить список моделей с Groq")
        self.refresh_btn.clicked.connect(self._refresh_models)
        model_row.addWidget(self.refresh_btn)
        left_l.addLayout(model_row)

        left_l.addWidget(QLabel("Тема / текст:"))
        self.topic_edit = QPlainTextEdit()
        self.topic_edit.setPlaceholderText("Например: обзор кафе «Дом»")
        self.topic_edit.setFixedHeight(110)
        left_l.addWidget(self.topic_edit)

        dur_row = QHBoxLayout()
        dur_row.addWidget(QLabel("Длит., мин:"))
        self.dur_spin = QSpinBox()
        self.dur_spin.setRange(1, 180)
        self.dur_spin.setValue(5)
        dur_row.addWidget(self.dur_spin, 1)
        left_l.addLayout(dur_row)

        style_row = QHBoxLayout()
        style_row.addWidget(QLabel("Стиль:"))
        self.style_combo = QComboBox()
        self.style_combo.addItems(
            ["обучающее", "влог", "разбор", "обзор", "история", "ивент/репортаж"]
        )
        style_row.addWidget(self.style_combo, 1)
        left_l.addLayout(style_row)

        wpm_row = QHBoxLayout()
        wpm_row.addWidget(QLabel("Слов/мин:"))
        self.wpm_spin = QSpinBox()
        self.wpm_spin.setRange(80, 250)
        self.wpm_spin.setValue(150)
        wpm_row.addWidget(self.wpm_spin, 1)
        left_l.addLayout(wpm_row)

        temp_row = QHBoxLayout()
        temp_row.addWidget(QLabel("Креатив:"))
        self.temp_combo = QComboBox()
        self.temp_combo.addItems(["0.3 — строго", "0.7 — баланс", "1.0 — креатив"])
        self.temp_combo.setCurrentIndex(1)
        temp_row.addWidget(self.temp_combo, 1)
        left_l.addLayout(temp_row)

        left_l.addStretch()

        self.run_btn = QPushButton("▶  Сгенерировать")
        self.run_btn.setMinimumHeight(46)
        self.run_btn.setObjectName("runBtn")
        self.run_btn.clicked.connect(self._run)
        left_l.addWidget(self.run_btn)

        splitter.addWidget(left)

        # ===== ПРАВАЯ ПАНЕЛЬ =====
        right = QWidget()
        right_l = QVBoxLayout(right)
        right_l.setContentsMargins(6, 0, 0, 0)
        right_l.setSpacing(8)

        header = QHBoxLayout()
        header.addWidget(self._section("Результат (Markdown)"))
        header.addStretch()

        self.source_btn = QPushButton("👁 Исходник")
        self.source_btn.setCheckable(True)
        self.source_btn.setToolTip("Показать/скрыть исходный markdown-текст")
        self.source_btn.clicked.connect(self._toggle_source)
        header.addWidget(self.source_btn)

        self.stars_btn = QPushButton("🧹 Убрать разметку")
        self.stars_btn.setToolTip("Убирает *, #, таблицы, эмодзи — оставляет чистый текст")
        self.stars_btn.setObjectName("starsBtn")
        self.stars_btn.clicked.connect(self._strip_stars)
        header.addWidget(self.stars_btn)

        self.copy_btn = QPushButton("📋 Копировать")
        self.copy_btn.clicked.connect(self._copy)
        header.addWidget(self.copy_btn)

        self.save_btn = QPushButton("💾 Сохранить")
        self.save_btn.clicked.connect(self._save_file)
        header.addWidget(self.save_btn)

        self.clear_btn = QPushButton("🗑 Очистить")
        self.clear_btn.clicked.connect(self._clear_output)
        header.addWidget(self.clear_btn)

        right_l.addLayout(header)

        # --- inner splitter: preview + history ---
        inner_split = QSplitter(Qt.Horizontal)

        self.output = QWebEngineView()
        self.output.setHtml(self._wrap_html(""))
        inner_split.addWidget(self.output)

        self.source_view = QPlainTextEdit()
        self.source_view.setReadOnly(True)
        self.source_view.setVisible(False)
        self.source_view.setStyleSheet(
            "QPlainTextEdit{background:#15161a;color:#e6e6e6;"
            "font-family:Consolas,monospace;font-size:13px;}"
        )
        inner_split.addWidget(self.source_view)

        # history
        hist_widget = QWidget()
        hist_l = QVBoxLayout(hist_widget)
        hist_l.setContentsMargins(6, 0, 0, 0)
        hist_l.setSpacing(6)

        hist_header = QHBoxLayout()
        hist_header.addWidget(self._section("История"))
        hist_header.addStretch()
        self.clear_hist_btn = QPushButton("🗑")
        self.clear_hist_btn.setFixedWidth(34)
        self.clear_hist_btn.setToolTip("Очистить всю историю")
        self.clear_hist_btn.clicked.connect(self._clear_history)
        hist_header.addWidget(self.clear_hist_btn)
        hist_l.addLayout(hist_header)

        self.history_list = QListWidget()
        self.history_list.itemClicked.connect(self._load_from_history)
        self.history_list.setWordWrap(True)
        hist_l.addWidget(self.history_list, 1)

        inner_split.addWidget(hist_widget)
        inner_split.setSizes([760, 220])

        right_l.addWidget(inner_split, 1)

        self.status = QLabel("Готов к работе")
        self.status.setStyleSheet("color:#888;")
        right_l.addWidget(self.status)

        splitter.addWidget(right)
        splitter.setSizes([340, 1010])

    def _section(self, text):
        lbl = QLabel(text.upper())
        lbl.setStyleSheet("color:#7aa2f7; font-weight:bold; padding-top:6px;")
        return lbl

    def _apply_style(self):
        self.setStyleSheet("""
            QMainWindow, QWidget { background:#1e1f24; color:#e6e6e6; }
            QLineEdit, QPlainTextEdit, QSpinBox, QComboBox, QListWidget {
                background:#2a2c33; border:1px solid #3a3d47;
                border-radius:6px; padding:6px; color:#e6e6e6;
            }
            QLineEdit:focus, QPlainTextEdit:focus { border:1px solid #7aa2f7; }
            QListWidget::item { padding:6px; border-bottom:1px solid #2a2c33; }
            QListWidget::item:selected { background:#7aa2f7; color:#1e1f24; }
            QPushButton {
                background:#2a2c33; border:1px solid #3a3d47;
                border-radius:6px; padding:7px 12px; color:#e6e6e6;
            }
            QPushButton:hover { background:#333640; }
            QPushButton:checked {
                background:#7aa2f7; color:#1e1f24; border:1px solid #7aa2f7;
                font-weight:bold;
            }
            QPushButton#runBtn {
                background:#7aa2f7; color:#1e1f24;
                font-weight:bold; font-size:14px; border:none;
            }
            QPushButton#runBtn:hover { background:#8fb3ff; }
            QPushButton#runBtn:disabled { background:#4a5568; color:#999; }
            QPushButton#starsBtn {
                background:#4a3a52; border:1px solid #7a5aa2;
                color:#e0c9ff; font-weight:bold;
            }
            QPushButton#starsBtn:hover { background:#5a4a62; }
            QSplitter::handle { background:#2a2c33; }
        """)

    # ---------------- HTML-обёртка ----------------
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
  img {{ max-width:100%; border-radius:6px; }}
</style></head><body>{body}</body></html>"""

    def _render_markdown(self):
        html_body = markdown2.markdown(
            self._md_buffer,
            extras=["tables", "fenced-code-blocks", "strike", "task_list"],
        )
        self.output.setHtml(self._wrap_html(html_body))
        self.source_view.setPlainText(self._md_buffer)
        QTimer.singleShot(60, lambda: self.output.page().runJavaScript(
            "window.scrollTo(0, document.body.scrollHeight);"
        ))

    # ---------------- Настройки ----------------
    def _load_settings(self):
        key = self.settings.value("api_key", "")
        if key:
            self.key_edit.setText(key)
        self.temp_combo.setCurrentIndex(int(self.settings.value("temp", 1)))

    def _save_key(self):
        self.settings.setValue("api_key", self.key_edit.text().strip())
        self.status.setText("API-ключ сохранён")

    def _toggle_key(self):
        if self.key_edit.echoMode() == QLineEdit.Password:
            self.key_edit.setEchoMode(QLineEdit.Normal)
        else:
            self.key_edit.setEchoMode(QLineEdit.Password)

    def _refresh_models(self):
        key = self.key_edit.text().strip()
        if not key:
            QMessageBox.warning(self, "Нет ключа", "Сначала вставь API-ключ.")
            return
        try:
            client = Groq(api_key=key)
            ids = [m.id for m in client.models.list().data]
            chat_models = [m for m in ids if not any(
                x in m.lower() for x in ("whisper", "tts", "guard", "prompt-guard")
            )]
            chat_models.sort()
            self.model_combo.clear()
            self.model_combo.addItems(chat_models)
            self.status.setText(f"Загружено моделей: {len(chat_models)}")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))

    # ---------------- Задачи ----------------
    def _select_task(self, task_id):
        self.current_task = task_id
        for tid, btn in self.task_buttons.items():
            btn.setChecked(tid == task_id)

        hints = {
            "ideas":    "Опиши тему или нишу — верну 10 идей.",
            "shooting": "Что снимаем? Например: обзор кафе «Дом», 15 мин от метро.",
            "hooks":    "О чём видео? Верну варианты хуков.",
            "script":   "Тема видео. Учту длительность и стиль.",
            "improve":  "Вставь свой текст сценария — перепишу.",
            "timing":   "Вставь сценарий — разобью на блоки по времени.",
            "titles":   "Тема — верну 15 заголовков.",
        }
        self.topic_edit.setPlaceholderText(hints.get(task_id, ""))

        show_template = task_id == "shooting"
        self.template_label.setVisible(show_template)
        self.template_combo.setVisible(show_template)

        self.dur_spin.setEnabled(task_id == "script")
        self.style_combo.setEnabled(task_id == "script")
        self.wpm_spin.setEnabled(task_id == "timing")

    # ---------------- Промпты ----------------
    def _build_prompt(self):
        topic = self.topic_edit.toPlainText().strip()
        if not topic:
            QMessageBox.warning(self, "Пусто", "Заполни поле «Тема / текст».")
            return None

        if self.current_task == "ideas":
            return (f"Дай 10 идей видео на тему «{topic}». Для каждой: заголовок, "
                    f"одно предложение сути, почему зайдёт. Нумерованным списком.")

        if self.current_task == "shooting":
            template_name = self.template_combo.currentText()
            template_body = TEMPLATES.get(template_name, "")
            return (
                f"Составь ХРОНОЛОГИЧЕСКИЙ план съёмки и монтажа видео на тему: «{topic}».\n\n"
                f"Используй как основу этот шаблон хронологии:\n{template_body}\n\n"
                f"Оформи ответ как markdown-таблицу с колонками:\n"
                f"№ | Этап (название сцены) | Что снимаем (планы) | Длительность, с | "
                f"На что обратить внимание.\n\n"
                f"Адаптируй шаблон под конкретную тему (убери лишнее, добавь нужное).\n\n"
                f"После таблицы добавь два блока:\n"
                f"## Кадры, которые легко забыть снять\n"
                f"5–7 пунктов списком.\n\n"
                f"## Идеи для хука (первые 5 сек)\n"
                f"3 варианта с коротким пояснением."
            )

        if self.current_task == "hooks":
            return (f"Придумай 5 вариантов хуков (первые 5 секунд) для видео: «{topic}». "
                    f"Разные приёмы: вопрос, шок-факт, интрига, обещание, конфликт. "
                    f"Для каждого: текст хука и одним предложением почему цепляет.")

        if self.current_task == "script":
            dur = self.dur_spin.value()
            style = self.style_combo.currentText()
            return (f"Напиши полный сценарий видео.\nТема: {topic}\n"
                    f"Длительность: {dur} мин\nСтиль: {style}\n\n"
                    f"Формат: блоки с таймингами (0:00–0:15 и т.д.), в каждом — что говорим "
                    f"и что показываем на экране (B-roll, текст). Речь дословно, чтобы "
                    f"можно было читать в камеру.")

        if self.current_task == "improve":
            return ("Улучши этот сценарий: убери воду и клише, усиль формулировки, "
                    "сохрани смысл и мой стиль. Покажи «до/после» по абзацам.\n\n"
                    f"Текст:\n{topic}")

        if self.current_task == "timing":
            wpm = self.wpm_spin.value()
            return (f"Разбей сценарий на блоки по таймингу, исходя из {wpm} слов/мин. "
                    f"Оформи как markdown-таблицу: Время | Текст | Что на экране.\n\n{topic}")

        if self.current_task == "titles":
            return (f"Придумай 15 цепляющих заголовков для видео на тему «{topic}». "
                    f"Разные стили: интрига, число, вопрос, обещание, конфликт.")

        return None

    # ---------------- Запуск ----------------
    def _run(self):
        if self.worker and self.worker.isRunning():
            return

        key = self.key_edit.text().strip()
        if not key:
            QMessageBox.warning(self, "Нет ключа", "Вставь Groq API-ключ сверху.")
            return

        prompt = self._build_prompt()
        if not prompt:
            return

        model = self.model_combo.currentText().strip()
        temp = [0.3, 0.7, 1.0][self.temp_combo.currentIndex()]

        self._md_buffer = ""
        self.output.setHtml(self._wrap_html(""))
        self.source_view.clear()

        self.run_btn.setEnabled(False)
        self.run_btn.setText("⏳ Генерация…")
        self.status.setText(f"Запрос к {model}…")

        self.worker = Worker(key, model, prompt, temp)
        self.worker.chunk.connect(self._on_chunk)
        self.worker.done.connect(self._on_done)
        self.worker.error.connect(self._on_error)
        self.worker.start()

    def _on_chunk(self, text):
        self._md_buffer += text
        if not self._render_timer.isActive():
            self._render_timer.start()

    def _on_done(self):
        self._render_timer.stop()
        self._render_markdown()
        self.run_btn.setEnabled(True)
        self.run_btn.setText("▶  Сгенерировать")
        text = self._md_buffer.strip()
        if text:
            self._push_history(text)
        self.status.setText("Готово")

    def _on_error(self, msg):
        self.run_btn.setEnabled(True)
        self.run_btn.setText("▶  Сгенерировать")
        self.status.setText("Ошибка")
        QMessageBox.critical(self, "Ошибка API", msg)

    # ---------------- Управление выводом ----------------
    def _clear_output(self):
        self._md_buffer = ""
        self.output.setHtml(self._wrap_html(""))
        self.source_view.clear()
        self.status.setText("Очищено")

    def _toggle_source(self):
        show = self.source_btn.isChecked()
        self.output.setVisible(not show)
        self.source_view.setVisible(show)

    def _strip_stars(self):
        if not self._md_buffer.strip():
            self.status.setText("Нечего чистить")
            return
        before = self._md_buffer
        self._md_buffer = strip_markdown(before)
        self._render_markdown()
        self.source_btn.setChecked(True)
        self.output.setVisible(False)
        self.source_view.setVisible(True)
        removed = len(before) - len(self._md_buffer)
        self.status.setText(f"Разметка убрана, удалено символов: {removed}")

    def _copy(self):
        text = self._md_buffer
        if text:
            QApplication.clipboard().setText(text)
            self.status.setText("Скопировано в буфер (markdown)")

    def _save_file(self):
        text = self._md_buffer.strip()
        if not text:
            QMessageBox.information(self, "Пусто", "Нечего сохранять.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить сценарий", "scenario.md",
            "Markdown (*.md);;Текст (*.txt)"
        )
        if path:
            Path(path).write_text(text, encoding="utf-8")
            self.status.setText(f"Сохранено: {path}")

    # ---------------- История ----------------
    def _load_history(self):
        if self.history_file.exists():
            try:
                return json.loads(self.history_file.read_text(encoding="utf-8"))
            except Exception:
                return []
        return []

    def _save_history(self):
        try:
            self.history_file.write_text(
                json.dumps(self.history, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    def _refresh_history_view(self):
        self.history_list.clear()
        for entry in self.history:
            label = f"{entry['time']}  ·  {entry['task']}\n{entry['preview']}"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, entry["text"])
            item.setToolTip(entry["text"][:400])
            self.history_list.addItem(item)

    def _push_history(self, text: str):
        task_names = {
            "ideas": "Идеи", "shooting": "План съёмки", "hooks": "Хуки",
            "script": "Сценарий", "improve": "Улучшение",
            "timing": "Тайминг", "titles": "Заголовки",
        }
        entry = {
            "time": datetime.now().strftime("%H:%M %d.%m"),
            "task": task_names.get(self.current_task, self.current_task or "—"),
            "preview": text.strip().split("\n", 1)[0][:60] + "…",
            "text": text,
        }
        self.history.insert(0, entry)
        self.history = self.history[:60]
        self._save_history()
        self._refresh_history_view()

    def _load_from_history(self, item):
        text = item.data(Qt.UserRole)
        if text:
            self._md_buffer = text
            self._render_markdown()
            self.source_btn.setChecked(False)
            self.output.setVisible(True)
            self.source_view.setVisible(False)
            self.status.setText("Загружено из истории")

    def _clear_history(self):
        if QMessageBox.question(
            self, "Очистить историю?",
            "Удалить все сохранённые генерации?",
        ) == QMessageBox.Yes:
            self.history = []
            self._save_history()
            self._refresh_history_view()
            self.status.setText("История очищена")

    # ---------------- Закрытие ----------------
    def closeEvent(self, e):
        self.settings.setValue("api_key", self.key_edit.text().strip())
        self.settings.setValue("temp", self.temp_combo.currentIndex())
        if self.worker and self.worker.isRunning():
            self.worker.terminate()
            self.worker.wait(500)
        super().closeEvent(e)


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()