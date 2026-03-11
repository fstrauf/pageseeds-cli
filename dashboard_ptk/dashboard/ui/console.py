"""
Console and styling setup
"""
from prompt_toolkit.styles import Style
from rich.console import Console

# Global console instance
console = Console()

# Prompt styling
style = Style.from_dict({
    'prompt': '#00aaff bold',
})
