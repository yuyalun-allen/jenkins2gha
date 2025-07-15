import json
import os

from openai import OpenAI
from converter.utils.getLogger import setup_logging
from dotenv import load_dotenv

logger = setup_logging()


def get_first_n_lines(text, n=3):
    """获取文本的前n行并添加省略号（如果有更多行）"""
    lines = text.split('\n')
    if len(lines) <= n:
        return text
    else:
        return '\n'.join(lines[:n]) + "\n... (省略剩余内容)"


def construct_system_prompt() -> str:
    """
    返回一个在 System 角色中发送给大模型的提示，
    用来强制约束大模型输出的风格与结构。
    """
    # 这里把“格式化”要求放在 system 消息中，以便提升遵从度
    system_instructions = (
        "You are a helpful assistant specialized in CI/CD pipeline configurations.\n"
        "You will receive a Jenkins pipeline config (as JSON) and some plugin documentation.\n\n"
        "Your task:\n"
        "1. Convert the Jenkins pipeline steps into GitHub Actions steps.\n"
        "2. **Output** them as a strict JSON array of steps, where each step is an object.\n"
        "3. Use the following fields for each step whenever possible:\n"
        "   - name: string (optional if 'uses' is present)\n"
        "   - uses: string (e.g. 'actions/checkout@v3')\n"
        "   - run: string (shell command)\n"
        "   - with: object (sub-keys for inputs)\n"
        "   - env: object (sub-keys for environment variables)\n"
        "4. Do NOT include markdown formatting or extra commentary. Only return valid JSON.\n"
        "5. Ensure the JSON can be parsed by standard JSON libraries without error.\n"
    )
    return system_instructions


def construct_prompt(jenkins_config, plugin_description):
    """
    构建发送给 GPT-4 的提示内容。
    :param jenkins_config: Jenkins 流水线配置文件内容（字典）
    :param plugin_description: 检索到的插件描述（字符串）
    :return: 构建好的提示字符串
    """
    prompt = (
        f"### Jenkins Pipeline Configuration (JSON):\n"
        f"{json.dumps(jenkins_config, ensure_ascii=False, indent=2)}\n\n"
        f"### Plugin Description:\n"
        f"{plugin_description}\n\n"
        "Now, please convert the above Jenkins configuration into a GitHub Actions configuration.\n"
        "Remember to return the result **strictly** as valid JSON.\n"
    )
    return prompt


def query_llm(prompt):
    """
    使用 OpenAI 框架库函数调用大模型生成响应。
    :param prompt: 提示内容
    :return: LLM 的响应
    """
    load_dotenv()
    llm_url = os.getenv("LLM_URL")
    sk = os.getenv("SK")
    model = os.getenv("MODEL")

    system_prompt = construct_system_prompt()

    # logger.info(f"=== System Prompt ===:\n{system_prompt} \n === System Prompt End ===")
    # logger.info(f"=== User Prompt ===:\n{prompt} \n === User Prompt End ===")

    # 使用函数处理日志输出
    system_prompt_preview = get_first_n_lines(system_prompt)
    prompt_preview = get_first_n_lines(prompt)

    logger.info(f"=== System Prompt (前3行) ===:\n {system_prompt_preview} \n === System Prompt End ===")
    logger.info(f"=== User Prompt (前3行) ===:\n {prompt_preview} \n === User Prompt End ===")

    try:
        client = OpenAI(api_key=sk, base_url=llm_url)
        # 调用API
        response = client.chat.completions.create(
            model=model,
            # model="deepseek-reasoner",
            # model="gpt-4-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            stream=False
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"LLM Error: {str(e)}"
