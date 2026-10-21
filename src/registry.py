from mmengine.registry import Registry

TOOL = Registry('tool', locations=['src.tools'])
AGENT = Registry('agent', locations=['src.agent'])