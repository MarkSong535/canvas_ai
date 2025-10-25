# 最小化配置示例
# 注意：模型配置通过环境变量管理，需在 .env 中设置：
# - OPENAI_API_KEY（可选：OPENAI_API_BASE / OPENAI_ORGANIZATION / OPENAI_PROJECT）

# GeneralAgent 配置
general_agent_config = dict(
    type="general_agent",  # Agent类型
    name="general_agent",  # Agent名称
    model_id="gpt-4o",  # 使用的模型ID
    description="A general purpose agent",  # 描述
    max_steps=10,  # 最大步数
    template_path="src/agent/general_agent/prompts/general_agent.yaml",  # Prompt模板路径
    tools=[],  # 工具列表（初始为空，可自定义添加）
    managed_agents=[],  # 托管Agent列表（初始为空）
)

# 主配置
agent_config = general_agent_config

