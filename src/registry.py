from mmengine.registry import Registry

DATASET = Registry('dataset', locations=['src.dataset'])
TOOL = Registry('tool', locations=['src.tools'])
AGENT = Registry('agent', locations=['src.agent'])