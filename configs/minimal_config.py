# Minimal configuration example
# Note: model settings are managed via environment variables in .env:
# - OPENAI_API_KEY (optional: OPENAI_API_BASE / OPENAI_ORGANIZATION / OPENAI_PROJECT)

# GeneralAgent configuration
general_agent_config = dict(
    type="general_agent",  # Agent type
    name="general_agent",  # Agent name
    model_id="gpt-4o",  # Model identifier to use
    description="A general purpose agent",  # Description
    max_steps=10,  # Maximum planning steps
    template_path="src/agent/general_agent/prompts/general_agent.yaml",  # Prompt template path
    tools=[],  # Tool list (empty by default; extend as needed)
    managed_agents=[],  # Managed agent list (empty by default)
)

# Primary configuration export
agent_config = general_agent_config

