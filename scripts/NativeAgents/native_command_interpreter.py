"""Command interpreter for NativeAgents experiments."""

import json
import re


class NativeCommandInterpreter:
    def __init__(self, model):
        self.model = model

    def parse(self, text: str):
        local = self._parse_local(text)
        if local is not None:
            return local, 'local'
        parsed = self._parse_ollama(text)
        return parsed, 'ollama' if parsed is not None else 'ollama-error'

    def _parse_local(self, text: str):
        lowered = str(text).strip().lower()
        if not lowered:
            return None
        if lowered in ('quit', 'exit'):
            return {'action': 'quit'}
        if lowered in ('status', 'where'):
            return {'action': 'status'}
        if lowered in ('look', 'scan'):
            return {'action': 'look'}
        if lowered in ('help',):
            return {'action': 'help'}
        semantic_tokens = ('nearest', 'closest', 'visible', 'building', 'store', 'shop', 'tree', 'trash', 'bin')
        if any(token in lowered for token in semantic_tokens):
            return {
                'action': 'semantic_goto',
                'query': lowered,
                'visible_only': 'visible' in lowered,
            }
        return None

    def _parse_ollama(self, text: str):
        system_prompt = (
            "You are a command parser for a native SimWorld humanoid test runner. "
            "Reply with exactly one JSON object and no markdown. "
            "Allowed actions are: planner_plan, semantic_goto, status, look, help, quit, unknown. "
            "Use semantic_goto when the user asks for nearest or visible world objects like building, store, tree, trash bin. "
            "Use planner_plan when the user gives a coordinate-like or general navigation instruction. "
            "Schema rules: "
            "{\"action\":\"semantic_goto\",\"query\":\"nearest building\",\"visible_only\":false}. "
            "{\"action\":\"semantic_goto\",\"query\":\"visible store\",\"visible_only\":true}. "
            "{\"action\":\"planner_plan\",\"plan\":\"go to [0, 0]\"}. "
            "{\"action\":\"status\"}. "
            "{\"action\":\"look\"}. "
            "{\"action\":\"help\"}. "
            "{\"action\":\"quit\"}. "
            "{\"action\":\"unknown\",\"raw_text\":\"...\"}."
        )
        response, _ = self.model.generate_text(system_prompt=system_prompt, user_prompt=text, max_tokens=256, temperature=0.0, top_p=1.0)
        if response is None:
            return None
        match = re.search(r'(\{.*\})', str(response), re.DOTALL)
        if not match:
            return None
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            return None
