# 最小化配置示例
# 注意：Azure OpenAI 的配置通过环境变量管理，请在 .env 文件中设置：
# - AZURE_OPENAI_ENDPOINT
# - AZURE_OPENAI_API_KEY  
# - AZURE_OPENAI_API_VERSION (默认: 2024-08-01-preview)

# GeneralAgent 配置
general_agent_config = dict(
    type="general_agent",  # Agent类型
    name="general_agent",  # Agent名称
    model_id="azure-gpt-4o",  # 使用的模型ID
    description="A general purpose agent",  # 描述
    max_steps=10,  # 最大步数
    template_path="src/agent/general_agent/prompts/general_agent.yaml",  # Prompt模板路径
    tools=[],  # 工具列表（初始为空，可自定义添加）
    managed_agents=[],  # 托管Agent列表（初始为空）
)

# 主配置
agent_config = general_agent_config

