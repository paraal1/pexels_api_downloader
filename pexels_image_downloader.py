import os
import requests
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QWidget, QLabel, QLineEdit,
    QSpinBox, QComboBox, QProgressBar, QTextEdit, QPushButton, QGroupBox, QFormLayout
)
from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt

# Replace with your Pexels API Key
API_FILE = open(r"pexels_api_downloader\api.txt", "r")
API_KEY = API_FILE.read()
API_FILE.close()

HEADERS = {"Authorization": API_KEY}
BASE_URL_IMAGE = "https://api.pexels.com/v1/search"
BASE_URL_VIDEO = "https://api.pexels.com/videos/search"
DOWNLOAD_DIR_IMAGES = "pexels_api_downloader\Pexels_Images"
DOWNLOAD_DIR_VIDEOS = "pexels_api_downloader\Pexels_Images"

os.makedirs(DOWNLOAD_DIR_IMAGES, exist_ok=True)
os.makedirs(DOWNLOAD_DIR_VIDEOS, exist_ok=True)


# Worker thread for downloading files
class DownloadWorker(QThread):
    progress = pyqtSignal(int)
    log = pyqtSignal(str)
    rate_limit_update = pyqtSignal(dict)
    stop_requested = pyqtSignal()  # Signal to request stopping the download

    def __init__(self, query, num_files, input_type, options):
        super().__init__()
        self.query = query
        self.num_files = min(num_files, 1000)  # Cap at 1000 files as a practical limit
        self.input_type = input_type
        self.options = options
        self._stop_flag = False  # Flag to indicate if the download should stop

    def run(self):
        image = 1
        video = 2
        params = {"query": self.query, "per_page": 80, **self.options}
        total_downloaded = 0
        current_page = 1

        if self.input_type == image:
            base_url = BASE_URL_IMAGE
            download_dir = DOWNLOAD_DIR_IMAGES
            file_key = "photos"
            file_url_key = "src"
            file_url_subkey = "original" if self.options.get("format") == "original" else "large"
            file_extension = ".jpg"
        elif self.input_type == video:
            base_url = BASE_URL_VIDEO
            download_dir = DOWNLOAD_DIR_VIDEOS
            file_key = "videos"
            file_url_key = "video_files"
            file_url_subkey = "link"
            file_extension = ".mp4"
        else:
            self.log.emit("Invalid file type selected.")
            return

        download_tasks = []

        while total_downloaded < self.num_files:
            if self._stop_flag:
                self.log.emit("Download stopped by user.")
                return

            params["page"] = current_page
            response = requests.get(base_url, headers=HEADERS, params=params)

            # Check API rate limits
            if "X-Ratelimit-Limit" in response.headers:
                limit = response.headers["X-Ratelimit-Limit"]
                remaining = response.headers["X-Ratelimit-Remaining"]
                reset_time = response.headers["X-Ratelimit-Reset"]
                reset_time_formatted = datetime.fromtimestamp(int(reset_time)).strftime('%Y-%m-%d %H:%M:%S')
                self.rate_limit_update.emit({
                    "limit": limit,
                    "remaining": remaining,
                    "reset_time": reset_time_formatted
                })

            if response.status_code != 200:
                self.log.emit(f"Error: Unable to fetch files. Status code: {response.status_code}")
                break

            files = response.json().get(file_key, [])
            if not files:
                break  # No more files available

            for i, file in enumerate(files):
                if total_downloaded >= self.num_files:
                    break

                if self.input_type == image:
                    file_url = file.get(file_url_key, {}).get(file_url_subkey, "")
                elif self.input_type == video:
                    file_url = next((vfile[file_url_subkey] for vfile in file.get(file_url_key, []) if vfile["quality"] == self.options.get("quality", "hd")), None)

                if file_url:
                    file_name = os.path.join(download_dir, f"{self.query}_{total_downloaded + 1}{file_extension}")
                    download_tasks.append((file_url, file_name))
                    total_downloaded += 1

            current_page += 1

        total_tasks = len(download_tasks)
        completed_tasks = 0

        with ThreadPoolExecutor(max_workers=5) as executor:
            for file_info in download_tasks:
                if self._stop_flag:
                    self.log.emit("Download stopped by user.")
                    return
                self.download_file(file_info)
                completed_tasks += 1
                self.progress.emit(int((completed_tasks / total_tasks) * 100))

        self.log.emit("All files downloaded.")

    def download_file(self, file_info):
        file_url, file_name = file_info
        try:
            with requests.get(file_url, stream=True) as response:
                response.raise_for_status()
                total_size = int(response.headers.get('content-length', 0))
                downloaded_size = 0
                chunk_size = 1024
                with open(file_name, "wb") as f:
                    for chunk in response.iter_content(chunk_size=chunk_size):
                        if chunk:
                            f.write(chunk)
                            downloaded_size += len(chunk)
        except Exception as e:
            print(f"Failed to download {file_name}: {e}")

    def stop(self):
        self._stop_flag = True
        self.stop_requested.emit()  # Emit signal that download should be stopped


# Main GUI application
class PexelsDownloaderApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Pexels Downloader")
        self.setGeometry(100, 100, 900, 500)  # Adjusted window size
        self.setStyleSheet("background-color: #2d2d2d; color: #f0f0f0;")

        # Main layout
        main_layout = QVBoxLayout()

        # Title
        title = QLabel("Pexels Downloader")
        title.setFont(QFont("Arial", 22))
        title.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title)

        # Form layout for inputs
        form_layout = QFormLayout()

        # Query Input
        self.query_input = QLineEdit()
        self.query_input.setPlaceholderText("Enter search query (e.g., nature, ocean)")
        self.query_input.setStyleSheet("background-color: #3d3d3d; color: #f0f0f0;")
        form_layout.addRow("Search Query:", self.query_input)

        # Number of Files
        self.num_files_input = QSpinBox()
        self.num_files_input.setRange(1, 1000)
        self.num_files_input.setValue(5)
        self.num_files_input.setStyleSheet("background-color: #3d3d3d; color: #f0f0f0;")
        form_layout.addRow("Number of Files:", self.num_files_input)

        # File Type
        self.file_type_input = QComboBox()
        self.file_type_input.addItems(["Images", "Videos"])
        self.file_type_input.setStyleSheet("background-color: #3d3d3d; color: #f0f0f0;")
        form_layout.addRow("File Type:", self.file_type_input)

        # Custom Options
        self.format_input = QComboBox()
        self.format_input.addItems(["original", "large", "medium", "small"])
        self.format_input.setStyleSheet("background-color: #3d3d3d; color: #f0f0f0;")
        form_layout.addRow("Format (Images Only):", self.format_input)

        self.quality_input = QComboBox()
        self.quality_input.addItems(["hd", "sd"])
        self.quality_input.setStyleSheet("background-color: #3d3d3d; color: #f0f0f0;")
        form_layout.addRow("Quality (Videos Only):", self.quality_input)

        main_layout.addLayout(form_layout)

        # Progress Bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setStyleSheet("QProgressBar {background-color: #3d3d3d; color: #f0f0f0; text-align: center; border: 1px solid #555;}")
        main_layout.addWidget(self.progress_bar)

        # Buttons layout
        button_layout = QHBoxLayout()
        
        # Start Button
        start_button = QPushButton("Start Download")
        start_button.clicked.connect(self.start_download)
        start_button.setStyleSheet("background-color: #5a5a5a; color: #ffffff; padding: 10px;")
        button_layout.addWidget(start_button)

        # Stop Button
        stop_button = QPushButton("Stop Download")
        stop_button.clicked.connect(self.stop_download)
        stop_button.setStyleSheet("background-color: #a05a5a; color: #ffffff; padding: 10px;")
        button_layout.addWidget(stop_button)

        main_layout.addLayout(button_layout)

        # Log Output
        self.output_log = QTextEdit()
        self.output_log.setReadOnly(True)
        self.output_log.setStyleSheet("background-color: #3d3d3d; color: #f0f0f0; border: 1px solid #555;")
        main_layout.addWidget(self.output_log)

        # API Request Info
        self.api_info = QLabel("API Rate Limit Info will appear here.")
        self.api_info.setStyleSheet("background-color: #3d3d3d; color: #f0f0f0; padding: 5px;")
        main_layout.addWidget(self.api_info)

        # Set main layout to central widget
        central_widget = QWidget()
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)

        self.downloader = None

    def start_download(self):
        query = self.query_input.text()
        num_files = self.num_files_input.value()
        input_type = 1 if self.file_type_input.currentIndex() == 0 else 2
        options = {
            "format": self.format_input.currentText(),
            "quality": self.quality_input.currentText()
        }

        self.downloader = DownloadWorker(query, num_files, input_type, options)
        self.downloader.progress.connect(self.update_progress)
        self.downloader.log.connect(self.update_log)
        self.downloader.stop_requested.connect(self.on_stop_requested)
        self.downloader.rate_limit_update.connect(self.update_rate_limit_info)
        self.downloader.start()

    def stop_download(self):
        if self.downloader:
            self.downloader.stop()

    def update_progress(self, value):
        self.progress_bar.setValue(value)

    def update_log(self, message):
        self.output_log.append(message)

    def on_stop_requested(self):
        self.progress_bar.setValue(0)
        self.output_log.append("Download stopped by user.")

    def update_rate_limit_info(self, info):
        self.api_info.setText(f"Limit: {info['limit']} | Remaining: {info['remaining']} | Reset: {info['reset_time']}")

if __name__ == "__main__":
    app = QApplication([])
    window = PexelsDownloaderApp()
    window.show()
    app.exec_()
