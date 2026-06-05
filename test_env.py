import os


def mask_secret(value: str) -> str:
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def main() -> None:
    from dotenv import load_dotenv
    print(f".env exists: {os.path.exists('.env')}")
    print(f"before load: {'DASHSCOPE_API_KEY' in os.environ}")

    load_dotenv()

    api_key = os.environ.get("DASHSCOPE_API_KEY")
    print(f"after load: {api_key is not None}")

    if api_key:
        print(f"key preview: {mask_secret(api_key)}")
        print(f"key length: {len(api_key)}")
    else:
        print("DASHSCOPE_API_KEY not found")

    # 模型配置检查
    try:
        from model_config import validate_model_configs, get_config_summary
        warnings = validate_model_configs()
        if warnings:
            for w in warnings:
                print(f"WARNING: {w}")
        else:
            print("模型配置校验通过")
        print("模型配置：")
        print(get_config_summary())
    except Exception as e:
        print(f"模型配置检查失败: {e}")


if __name__ == "__main__":
    main()
