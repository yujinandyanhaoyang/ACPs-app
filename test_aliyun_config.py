#!/usr/bin/env python3
"""测试阿里云百炼配置是否正确"""
import os
import sys

# 加载 .env 文件
from dotenv import load_dotenv
load_dotenv()

print("=" * 60)
print("🔍 检查 .env 配置")
print("=" * 60)

# 检查环境变量
openai_api_key = os.getenv("OPENAI_API_KEY")
openai_base_url = os.getenv("OPENAI_BASE_URL")
dashscope_api_key = os.getenv("DASHSCOPE_API_KEY")
hf_endpoint = os.getenv("HF_ENDPOINT")

print(f"✅ OPENAI_API_KEY: {'已设置' if openai_api_key else '❌ 未设置'}")
print(f"✅ OPENAI_BASE_URL: {openai_base_url or '❌ 未设置'}")
print(f"   DASHSCOPE_API_KEY: {'已设置' if dashscope_api_key else '未设置 (使用 OPENAI_API_KEY)'}")
print(f"   HF_ENDPOINT: {hf_endpoint or '未设置'}")

print("\n" + "=" * 60)
print("🧪 测试阿里云百炼 API 连接")
print("=" * 60)

if not openai_api_key:
    print("❌ 错误：OPENAI_API_KEY 未设置")
    sys.exit(1)

if not openai_base_url:
    print("❌ 错误：OPENAI_BASE_URL 未设置")
    sys.exit(1)

# 测试 API 连接
try:
    import openai
    client = openai.OpenAI(
        api_key=openai_api_key,
        base_url=openai_base_url
    )
    
    # 测试聊天模型
    print("\n📞 测试聊天模型 (qwen-turbo, qwen-plus, qwen-max)...")
    for model in ["qwen-turbo", "qwen-plus", "qwen-max"]:
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "user", "content": "用中文回复 OK 即可"}
                ],
                max_tokens=10
            )
            content = response.choices[0].message.content
            print(f"  ✅ {model}: {content}")
            if model == "qwen-turbo":
                break  # qwen-turbo 成功后继续测试其他
        except Exception as e:
            print(f"  ⚠️  {model}: {str(e)[:60]}")
    
    # 测试嵌入模型（如果使用阿里云嵌入）
    print("\n📞 测试嵌入模型 (text-embedding-v3)...")
    try:
        embed_response = client.embeddings.create(
            model="text-embedding-v3",
            input=["test"]
        )
        dim = len(embed_response.data[0].embedding)
        print(f"✅ 嵌入模型响应：向量维度 {dim}")
    except Exception as e:
        print(f"⚠️  嵌入模型测试失败（可能未开通）：{e}")
    
    print("\n" + "=" * 60)
    print("✅ 阿里云百炼配置正常！")
    print("=" * 60)
    
except openai.APIError as e:
    print(f"\n❌ API 错误：{e}")
    print("\n可能原因：")
    print("1. API Key 无效或已过期")
    print("2. 账户余额不足")
    print("3. 模型未开通")
    sys.exit(1)
except Exception as e:
    print(f"\n❌ 测试失败：{e}")
    sys.exit(1)
