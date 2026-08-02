"""Local offline engine using llama.cpp."""
import os
import shlex
import shutil
import subprocess


class LocalEngine:
    def __init__(self, config):
        self.config = config
        self.model_path = config.get("local_model_path", "")
        self.binary = config.get("local_binary", "llama-cli")

    @property
    def available(self):
        return (
            bool(self.model_path)
            and os.path.isfile(self.model_path)
            and shutil.which(self.binary) is not None
        )

    def chat(self, messages, temperature=0.7):
        if not self.available:
            raise RuntimeError(
                "Local model not available (model file or llama-cli missing)"
            )
        system_parts = [m["content"] for m in messages if m["role"] == "system"]
        history = [m for m in messages if m["role"] in ("user", "assistant")]

        prompt = []
        if system_parts:
            prompt.append(f"<|system|>\n{system_parts[-1]}</s>")
        for msg in history:
            role = msg["role"]
            if role == "user":
                prompt.append(f"<|user|>\n{msg['content']}</s>")
            else:
                prompt.append(f"<|assistant|>\n{msg['content']}</s>")
        prompt.append("<|assistant|>\n")
        full_prompt = "".join(prompt)

        cmd = [
            self.binary,
            "-m",
            self.model_path,
            "-p",
            full_prompt,
            "--temp",
            str(temperature),
            "-n",
            "512",
            "--no-display-prompt",
        ]
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120
            )
        except subprocess.TimeoutExpired:
            return "Local model timed out (please retry)."
        except FileNotFoundError:
            return "llama-cli is not installed."
        return result.stdout.strip() or "Local model produced no output."
