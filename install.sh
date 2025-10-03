#!/bin/bash

# Скрипт для автоматической установки и настройки проекта verst_analyzer
# Убедитесь, что вы запускаете его из директории, в которой лежит папка проекта.

# --- Переменные --- #
PROJECT_DIR_NAME="verst_analyzer"
# Определяем абсолютный путь к директории проекта
PROJECT_DIR=$(realpath "$PROJECT_DIR_NAME")
# Определяем имя пользователя, от которого запускается скрипт
RUN_USER=$(whoami)

# --- Функции --- #

echo_green() {
    echo -e "\033[0;32m$1\033[0m"
}

echo_red() {
    echo -e "\033[0;31m$1\033[0m"
}

# --- Начало --- #

echo_green "Начинаем установку анализатора 5 вёрст..."

# Проверка, что директория проекта существует
if [ ! -d "$PROJECT_DIR" ]; then
    echo_red "Ошибка: Директория проекта '$PROJECT_DIR' не найдена. Убедитесь, что скрипт находится рядом с папкой проекта."
    exit 1
fi

# Шаг 1: Создание виртуального окружения
echo_green "\nШаг 1: Создание виртуального окружения..."
python3 -m venv --copies "$PROJECT_DIR/venv"
if [ $? -ne 0 ]; then
    echo_red "Не удалось создать виртуальное окружение. Убедитесь, что у вас установлен пакет python3-venv."
    exit 1
fi

# Шаг 2: Установка зависимостей
echo_green "\nШаг 2: Установка зависимостей..."
"$PROJECT_DIR/venv/bin/pip" install -r "$PROJECT_DIR/requirements.txt"
if [ $? -ne 0 ]; then
    echo_red "Не удалось установить зависимости. Проверьте файл requirements.txt и доступ к интернету."
    exit 1
fi

# Шаг 3: Сбор данных
echo_green "\nШаг 3: Первичный сбор данных..."
SCRAPE_FLAG="--full"
LOCATION_SLUG=""

# Проверяем, был ли передан флаг локации
if [ $# -gt 0 ]; then
    if [[ $1 == --* ]]; then
        LOCATION_SLUG=$1
        echo "Выбран режим для одной локации: ${LOCATION_SLUG:2}"
        SCRAPE_FLAG=$LOCATION_SLUG
    fi
fi

"$PROJECT_DIR/venv/bin/python" "$PROJECT_DIR/main.py" "$SCRAPE_FLAG"
if [ $? -ne 0 ]; then
    echo_red "Сбор данных завершился с ошибкой."
    exit 1
fi
echo_green "Сбор данных успешно завершен."

# Шаг 4: Настройка systemd
echo_green "\nШаг 4: Настройка системного сервиса (systemd)..."

SERVICE_FILE_CONTENT="[Unit]\nDescription=Gunicorn instance to serve verst_analyzer\nAfter=network.target\n\n[Service]\nUser=$RUN_USER\nGroup=$RUN_USER\nWorkingDirectory=$PROJECT_DIR\nEnvironment=\"PATH=$PROJECT_DIR/venv/bin\"\nExecStart=$PROJECT_DIR/venv/bin/gunicorn --workers 3 --bind unix:$PROJECT_DIR/verst_analyzer.sock -m 007 app:app\n\n[Install]\nWantedBy=multi-user.target"

echo "$SERVICE_FILE_CONTENT" | sudo tee /etc/systemd/system/verst_analyzer.service > /dev/null

echo "Перезагрузка и запуск сервиса..."
sudo systemctl daemon-reload
sudo systemctl enable verst_analyzer
sudo systemctl start verst_analyzer

# Даем сервису время на запуск
sleep 2

sudo systemctl status verst_analyzer --no-pager
if [ $? -ne 0 ]; then
    echo_red "Сервис systemd не запустился. Проверьте лог выше."
    exit 1
fi
echo_green "Сервис успешно запущен."

# Шаг 5: Настройка cron
echo_green "\nШаг 5: Настройка cron для автоматического обновления..."
CRON_JOB="0 * * * * $PROJECT_DIR/venv/bin/python $PROJECT_DIR/main.py >> $PROJECT_DIR/scraper.log 2>&1"
(crontab -l 2>/dev/null | grep -v -F "$PROJECT_DIR/main.py" ; echo "$CRON_JOB") | crontab -
if [ $? -ne 0 ]; then
    echo_red "Не удалось настроить cron. Пожалуйста, добавьте строку вручную, выполнив 'crontab -e'."
else
    echo_green "Cron успешно настроен."
fi

echo_green "\nУстановка завершена!"
echo "- Ваше приложение работает в фоновом режиме."
echo "- Данные будут автоматически обновляться каждый час."
echo "- Вам осталось настроить веб-сервер (Nginx) для доступа к приложению, если это необходимо."
