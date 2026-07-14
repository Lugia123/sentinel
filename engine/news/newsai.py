"""news 域 AI 客户端:读 server/.env 的 DeepSeek 配置(OpenAI 兼容),提供 chat/批量分级。"""
import os, json, re

ENV = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "server", ".env")


def _env():
    d = {}
    with open(ENV) as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                d[k] = v
    return d


def client():
    from openai import OpenAI
    e = _env()
    return OpenAI(api_key=e["SENTINEL_DEEPSEEK_KEY"], base_url=e.get("SENTINEL_DEEPSEEK_BASE", "https://api.deepseek.com")), \
        e.get("SENTINEL_DEEPSEEK_MODEL", "deepseek-chat")


def chat(system, user, temperature=0.2, json_mode=False):
    cli, model = client()
    kw = dict(model=model, temperature=temperature,
              messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
    if json_mode:
        kw["response_format"] = {"type": "json_object"}
    r = cli.chat.completions.create(**kw)
    return r.choices[0].message.content


def extract_json(s):
    """从模型输出里抠 JSON(容错代码围栏/前后缀)。"""
    s = s.strip()
    if s.startswith("```"):
        s = re.sub(r"^```\w*\n?", "", s)
        s = re.sub(r"\n?```$", "", s).strip()
    i, j = s.find("{"), s.rfind("}")
    a, b = s.find("["), s.rfind("]")
    # 取最外层(对象或数组)
    if a >= 0 and (i < 0 or a < i):
        i, j = a, b
    if i >= 0 and j > i:
        s = s[i:j + 1]
    return json.loads(s)
