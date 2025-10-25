import os
from mmengine import Config as MMConfig
from argparse import Namespace

from dotenv import load_dotenv
load_dotenv(verbose=True)

from src.utils import assemble_project_path, Singleton
from src.logger import logger

def process_general(config: MMConfig) -> MMConfig:

    config.exp_path = assemble_project_path(os.path.join(config.workdir, config.tag))
    os.makedirs(config.exp_path, exist_ok=True)

    config.log_path = os.path.join(config.exp_path, getattr(config, 'log_path', 'dra.log'))
    logger.info(f"| Arguments Log file: {config.log_path}")

    if "save_path" in config:
        config.save_path = os.path.join(config.exp_path, getattr(config, 'save_path', 'dra.json'))

    return config

def process_mcp(config: MMConfig) -> MMConfig:
    if "mcp_tools_config" in config:
        mcp_servers = config['mcp_tools_config']['mcpServers']
        if 'LocalMCP' in mcp_servers:
            args = mcp_servers['LocalMCP'].get('args', {})
            args = [assemble_project_path(item) if item.endswith('.py') else item for item in args]
            config['mcp_tools_config']['mcpServers']['LocalMCP']['args'] = args
    return config

class Config(MMConfig, metaclass=Singleton):
    def __init__(self):
        super(Config, self).__init__()

    def init_config(self, config_path: str, args: Namespace) -> None:
        # Initialize the general configuration
        mmconfig = MMConfig.fromfile(filename=assemble_project_path(config_path))
        if 'cfg_options' not in args or args.cfg_options is None:
            cfg_options = dict()
        else:
            cfg_options = args.cfg_options
        for item in args.__dict__:
            if item not in ['config', 'cfg_options'] and args.__dict__[item] is not None:
                cfg_options[item] = args.__dict__[item]
        mmconfig.merge_from_dict(cfg_options)

        # Process general configuration
        mmconfig = process_general(mmconfig)

        # Process MCP configuration
        mmconfig = process_mcp(mmconfig)

        self.__dict__.update(mmconfig.__dict__)

config = Config()