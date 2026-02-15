import sounddevice as sd
import numpy as np
import os
import wave

def microphone_detect(duration=5, samplerate=16000, channels=1):
    """
    Records audio from the default microphone and saves as WAV (16kHz mono) in data/audio.
    """
    print(f"[Microphone] Recording {duration}s audio...")
    audio_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'data', 'audio')
    os.makedirs(audio_dir, exist_ok=True)
    audio_path = os.path.join(audio_dir, 'microphone_capture.wav')

    recording = sd.rec(int(duration * samplerate), samplerate=samplerate, channels=channels, dtype='int16')
    sd.wait()

    with wave.open(audio_path, 'w') as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)  # 16-bit audio
        wf.setframerate(samplerate)
        wf.writeframes(recording.tobytes())
    print(f"[Microphone] Audio saved to {audio_path}")
    return audio_path, duration

if __name__ == "__main__":
    microphone_detect()