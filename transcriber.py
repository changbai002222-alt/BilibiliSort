import os
import subprocess
from typing import Optional
from faster_whisper import WhisperModel

class AudioTranscriber:
    """音频转写服务，基于 faster-whisper 和 ffmpeg"""

    def __init__(self, model_size: str = "base", device: str = "cpu", compute_type: str = "int8"):
        """
        初始化 Whisper 模型
        :param model_size: tiny, base, small, medium, large-v3
        :param device: cpu 或 cuda
        :param compute_type: int8 或 float16
        """
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self._model = None

    @property
    def model(self):
        if self._model is None:
            print(f"[Whisper] 正在加载 faster-whisper 引擎 (model={self.model_size}, device={self.device})...")
            self._model = WhisperModel(self.model_size, device=self.device, compute_type=self.compute_type)
            print("[Whisper] 模型加载完成！")
        return self._model

    def download_audio_with_ffmpeg(self, stream_url: str, output_path: str, headers: Optional[dict] = None) -> bool:
        """利用已安装的 ffmpeg 直接将远程流下载并转为 16kHz 单声道 wav/mp3"""
        header_str = ""
        if headers:
            header_str = "".join([f"{k}: {v}\r\n" for k, v in headers.items()])

        cmd = ["ffmpeg", "-y"]
        if header_str:
            cmd.extend(["-headers", header_str])
        cmd.extend(["-i", stream_url, "-vn", "-ar", "16000", "-ac", "1", "-b:a", "64k", output_path])

        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            return True
        except subprocess.CalledProcessError as e:
            print(f"FFmpeg error: {e.stderr.decode('utf-8', errors='ignore')}")
            return False

    def transcribe(self, audio_file_path: str, language: str = "zh") -> str:
        """转录音频文件为文本"""
        if not os.path.exists(audio_file_path):
            raise FileNotFoundError(f"Audio file not found: {audio_file_path}")

        segments, info = self.model.transcribe(audio_file_path, language=language, beam_size=5)
        
        result_lines = []
        for segment in segments:
            m, s = divmod(int(segment.start), 60)
            result_lines.append(f"[{m:02d}:{s:02d}] {segment.text.strip()}")
            
        return "\n".join(result_lines)
