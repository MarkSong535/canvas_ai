"""
示例工具: 简单的计算器

这个文件展示了如何创建一个自定义工具
"""

from src.tools import AsyncTool, ToolResult
from src.registry import TOOL


@TOOL.register_module(name="calculator_tool", force=True)
class CalculatorTool(AsyncTool):
    """
    简单的计算器工具，可以执行基本的数学运算
    """
    
    name = "calculator_tool"
    description = "执行数学计算。可以计算加减乘除等基本运算。例如: '1+2*3', '(10-5)/2'"
    
    parameters = {
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "要计算的数学表达式，例如 '123 + 456'"
            }
        },
        "required": ["expression"],
        "additionalProperties": False
    }
    
    output_type = "any"
    
    async def forward(self, expression: str) -> ToolResult:
        """
        执行数学表达式计算
        
        Args:
            expression: 数学表达式字符串
            
        Returns:
            ToolResult: 包含计算结果或错误信息
        """
        try:
            # 使用eval计算表达式（注意：生产环境中应使用更安全的方法）
            result = eval(expression)
            
            return ToolResult(
                output=f"计算结果: {expression} = {result}",
                error=None
            )
            
        except Exception as e:
            return ToolResult(
                output=None,
                error=f"计算错误: {str(e)}"
            )


# 使用示例
if __name__ == "__main__":
    import asyncio
    
    async def test():
        calculator = CalculatorTool()
        
        # 测试计算
        result = await calculator.forward("123 + 456")
        print(result.output)  # 输出: 计算结果: 123 + 456 = 579
        
        result = await calculator.forward("10 * 20")
        print(result.output)  # 输出: 计算结果: 10 * 20 = 200
        
        # 测试错误处理
        result = await calculator.forward("1 / 0")
        print(result.error)  # 输出: 计算错误: division by zero
    
    asyncio.run(test())

