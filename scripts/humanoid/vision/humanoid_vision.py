import os
import sys

import numpy as np

from simworld.agent.humanoid import Humanoid
from simworld.communicator.communicator import Communicator

from scripts.humanoid.common import debug_log, get_walk_speed_cm_per_sec

_vision_pipeline = None
_vision_model = None
_vision_processor = None
_vision_device = None


def load_vision_pipeline(model_name: str = None):
    global _vision_pipeline, _vision_model, _vision_processor, _vision_device
    if _vision_pipeline is not None:
        return _vision_pipeline

    model_name = model_name or os.environ.get('VISION_MODEL', 'Salesforce/blip-image-captioning-base')

    try:
        import torch
        from transformers import AutoProcessor, BlipForConditionalGeneration
    except Exception as e:
        raise RuntimeError(
            "Vision import failed while loading BLIP captioning dependencies. "
            f"Python executable: {sys.executable}. "
            f"Original error: {type(e).__name__}: {e}"
        ) from e

    print(f'Loading vision model {model_name} (this may take a while)...')
    try:
        processor = AutoProcessor.from_pretrained(model_name)
        model = BlipForConditionalGeneration.from_pretrained(model_name)
        requested_device = os.environ.get('VISION_DEVICE', 'cpu').strip().lower()
        if requested_device == 'auto':
            device = 'cuda' if torch.cuda.is_available() else 'cpu'
        elif requested_device == 'cuda' and torch.cuda.is_available():
            device = 'cuda'
        else:
            device = 'cpu'
        model.to(device)
        _vision_model = model
        _vision_processor = processor
        _vision_device = device

        def _generate_captions(image, top_k=3):
            inputs = processor(images=image, return_tensors='pt')
            inputs = {key: value.to(device) for key, value in inputs.items()}
            outputs = model.generate(
                **inputs,
                num_beams=max(1, int(top_k)),
                num_return_sequences=1,
                max_new_tokens=40,
            )
            captions = processor.batch_decode(outputs, skip_special_tokens=True)
            return [{'generated_text': caption.strip()} for caption in captions if caption.strip()]

        _vision_pipeline = _generate_captions
    except Exception as e:
        raise RuntimeError(
            f'Failed to load vision model {model_name}. '
            f'Python executable: {sys.executable}. '
            f'Original error: {type(e).__name__}: {e}'
        ) from e

    return _vision_pipeline


def unload_vision_pipeline():
    global _vision_pipeline, _vision_model, _vision_processor, _vision_device
    if _vision_model is not None:
        try:
            if _vision_device == 'cuda':
                import torch
                del _vision_model
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
        except Exception:
            pass
    _vision_pipeline = None
    _vision_model = None
    _vision_processor = None
    _vision_device = None


def caption_current_view(comm: Communicator, hum: Humanoid, model_name: str = None, top_k: int = 3):
    try:
        img = comm.get_camera_observation(hum.camera_id, 'lit', mode='direct')
        debug_log(
            'camera_observation',
            {'camera_id': hum.camera_id, 'type': type(img).__name__, 'shape': getattr(img, 'shape', None), 'top_k': top_k},
        )
    except Exception as e:
        raise RuntimeError(f'Failed to get camera image: {e}')

    try:
        from PIL import Image
    except Exception as e:
        raise RuntimeError(
            "Vision image-processing imports failed. "
            f"Python executable: {sys.executable}. "
            f"Original error: {type(e).__name__}: {e}"
        ) from e

    pil = Image.fromarray(img.astype('uint8')) if isinstance(img, np.ndarray) else Image.fromarray(np.array(img))
    pipeline = load_vision_pipeline(model_name)
    outputs = pipeline(pil, top_k=top_k)
    debug_log('vision_model_outputs', outputs)

    captions = []
    for output in outputs:
        text = output.get('generated_text') or output.get('caption') or output.get('text') or str(output)
        captions.append(text)
    debug_log('vision_captions', captions)
    if os.environ.get('KEEP_VISION_MODEL_LOADED', '0') != '1':
        unload_vision_pipeline()
    return captions


def check_vision_dependencies():
    missing = []
    modules = (
        ('transformers', 'transformers'),
        ('PIL', 'pillow'),
        ('torch', 'torch'),
        ('numpy', 'numpy'),
    )
    for module_name, package_name in modules:
        try:
            __import__(module_name)
        except Exception:
            missing.append(package_name)
    return missing


def print_runtime_status(use_ollama: bool, ollama_model: str):
    print(f'Python executable: {sys.executable}')
    print(f'Ollama enabled: {use_ollama}')
    print(f'Ollama model: {ollama_model}')
    print(f'Estimated walk speed: {get_walk_speed_cm_per_sec():.1f} cm/s')
    print(f'Vision device: {os.environ.get("VISION_DEVICE", "cpu")}')
    print(f'Keep vision model loaded: {os.environ.get("KEEP_VISION_MODEL_LOADED", "0") == "1"}')
    missing = check_vision_dependencies()
    if missing:
        print('Vision captioning unavailable. Missing packages:', ', '.join(missing))
        print(f'Install into this Python with: "{sys.executable}" -m pip install {" ".join(missing)}')
    else:
        print('Vision captioning dependencies are installed.')
