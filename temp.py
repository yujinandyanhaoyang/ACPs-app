import os
from openai import OpenAI

client = OpenAI(
    api_key='sk-6bfa89621b0a4631b06f4b1adfb6b6ed',
    base_url="https://dashscope.aliyuncs.com/api/v2/apps/protocols/compatible-mode/v1",
)

response = client.responses.create(
    model="qwen3.5-flash",
    input="9.9和9.11哪个大？",
    extra_body={
        "enable_thinking": True  # 启用思考模式
    }
)

# 遍历输出项
for item in response.output:
    if item.type == "reasoning":
        # 打印推理过程摘要
        print("【推理过程】")
        for summary in item.summary:
            print(summary.text[:500])  # 截取前500字符
        print()
    elif item.type == "message":
        # 打印最终答案
        print("【最终答案】")
        print(item.content[0].text)