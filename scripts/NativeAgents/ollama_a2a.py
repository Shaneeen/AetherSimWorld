"""Ollama/OpenAI-compatible adapter for SimWorld LocalPlanner experiments."""

import json
import os
import re
import time
from typing import Any

from simworld.llm.base_llm import BaseLLM


class OllamaA2AAdapter(BaseLLM):
    """Small adapter that makes Ollama usable with SimWorld's planner-style APIs."""

    def __init__(self, model_name: str = None, url: str = None, provider: str = 'local'):
        model_name = model_name or os.environ.get('OLLAMA_MODEL', 'phi3')
        url = url or os.environ.get('OLLAMA_OPENAI_URL', 'http://localhost:11434/v1')
        super().__init__(model_name=model_name, url=url, provider=provider)

    def generate_instructions(
        self,
        system_prompt: str,
        user_prompt: str,
        images=None,
        max_tokens=None,
        temperature: float = 0.0,
        top_p: float = 1.0,
        response_format: Any = None,
    ):
        start_time = time.time()
        schema = self._schema_text(response_format)
        full_user_prompt = user_prompt
        if schema:
            full_user_prompt += f'\n\nReturn valid JSON matching this schema:\n{schema}'

        response, _ = self.generate_text(
            system_prompt=system_prompt,
            user_prompt=full_user_prompt,
            max_tokens=max_tokens or 512,
            temperature=temperature,
            top_p=top_p,
        )
        parsed = self._extract_json(response) if response is not None else None
        return parsed, time.time() - start_time

    def _schema_text(self, response_format: Any) -> str:
        if response_format is None:
            return ''
        if hasattr(response_format, 'to_json_schema') and callable(response_format.to_json_schema):
            return json.dumps(response_format.to_json_schema(), indent=2, default=str)
        if hasattr(response_format, 'model_json_schema') and callable(response_format.model_json_schema):
            return json.dumps(response_format.model_json_schema(), indent=2, default=str)
        return str(response_format)

    def _extract_json(self, text):
        if text is None:
            return None
        if isinstance(text, dict):
            return text
        match = re.search(r'(\{.*\})', str(text), re.DOTALL)
        if not match:
            return None
        raw = match.group(1)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            fixed = re.sub(r'\\(?!["\\/bfnrt]|u[0-9a-fA-F]{4})', r'\\\\', raw)
            try:
                return json.loads(fixed)
            except json.JSONDecodeError:
                return None
