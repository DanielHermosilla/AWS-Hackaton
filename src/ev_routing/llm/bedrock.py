import json
import os
from typing import Any, Dict, Optional

try:
    import boto3
except Exception:  # pragma: no cover
    boto3 = None  # type: ignore

try:
    from botocore.config import Config as BotocoreConfig
except Exception:  # pragma: no cover
    BotocoreConfig = None  # type: ignore


class BedrockClient:
    def __init__(self, region: Optional[str] = None, model_id: Optional[str] = None, profile: Optional[str] = None):
        self.region = region or os.getenv("AWS_DEFAULT_REGION", "us-east-1")
        self.model_id = model_id or os.getenv("BEDROCK_MODEL_ID")
        self.profile = profile or os.getenv("AWS_PROFILE")
        self._client = None

    def _get_client(self):
        if boto3 is None:
            raise RuntimeError("boto3 not installed")
        if self._client is None:
            session_kwargs = {}
            if self.profile:
                session_kwargs["profile_name"] = self.profile
            session = boto3.Session(**session_kwargs)
            client_kwargs = {"region_name": self.region}
            if BotocoreConfig is not None:
                client_kwargs["config"] = BotocoreConfig(
                    connect_timeout=5,
                    read_timeout=30,
                    retries={"max_attempts": 3, "mode": "standard"},
                )
            self._client = session.client("bedrock-runtime", **client_kwargs)
        return self._client

    def converse(self, messages: Any, max_tokens: int = 512, temperature: float = 0.0) -> Dict[str, Any]:
        client = self._get_client()
        body = client.converse(
            modelId=self.model_id,
            messages=messages,
            inferenceConfig={"maxTokens": max_tokens, "temperature": temperature},
        )
        return body

    def converse_json(self, prompt: str, max_tokens: int = 512) -> Dict[str, Any]:
        messages = [{"role": "user", "content": [{"text": prompt}]}]
        body = self.converse(messages, max_tokens=max_tokens)
        # Extract text
        text = ""
        try:
            for out in body.get("output", {}).get("message", {}).get("content", []):
                text += out.get("text", "")
        except Exception:
            pass
        # parse json
        try:
            return json.loads(text)
        except Exception:
            # try find json substring
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1:
                try:
                    return json.loads(text[start:end+1])
                except Exception:
                    pass
            return {"_raw": text, "_parse_error": True}