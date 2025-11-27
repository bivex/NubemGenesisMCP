#!/usr/bin/env python3
"""
Rich CLI - Interface mejorada con Rich para NubemSuperFClaude
Proporciona colores, tablas, progress bars y mejor UX
"""

from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.syntax import Syntax
from rich.markdown import Markdown
from rich.panel import Panel
from rich.layout import Layout
from rich.live import Live
from rich.prompt import Prompt, Confirm
from rich import print as rprint
from rich.tree import Tree
from typing import Optional, List, Dict, Any
import time
import asyncio

console = Console()

class RichCLI:
    """CLI mejorado con Rich para mejor experiencia de usuario"""

    def __init__(self):
        self.console = Console()
        self.history = []

    def print_banner(self):
        """Muestra banner de bienvenida"""
        banner = """
╔══════════════════════════════════════════════════════╗
║      [bold cyan]NubemSuperFClaude[/bold cyan] - Enhanced AI Platform      ║
║         [dim]39 AI Personas + Multi-LLM Support[/dim]         ║
╚══════════════════════════════════════════════════════╝
        """
        self.console.print(Panel(banner, style="cyan", border_style="bright_blue"))

    def show_personas_table(self, personas: List[Dict]):
        """Muestra tabla de personas IA disponibles"""
        table = Table(title="🤖 AI Personas Available", show_header=True, header_style="bold magenta")
        table.add_column("ID", style="cyan", width=20)
        table.add_column("Name", style="green")
        table.add_column("Specialty", style="yellow")
        table.add_column("Score", justify="right", style="blue")

        for persona in personas:
            table.add_row(
                persona.get('id', 'N/A'),
                persona.get('name', 'Unknown'),
                persona.get('specialty', 'General')[:40] + "...",
                f"{persona.get('score', 0):.2f}"
            )

        self.console.print(table)

    def show_loading(self, message: str = "Processing..."):
        """Muestra spinner de carga"""
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self.console
        ) as progress:
            task = progress.add_task(f"[cyan]{message}", total=None)
            time.sleep(2)  # Simular procesamiento

    async def show_async_loading(self, message: str, coro):
        """Muestra loading mientras ejecuta tarea asíncrona"""
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            console=self.console
        ) as progress:
            task = progress.add_task(f"[cyan]{message}", total=100)

            # Ejecutar tarea en paralelo
            result = None
            async def run_task():
                nonlocal result
                result = await coro

            task_future = asyncio.create_task(run_task())

            # Actualizar progress bar
            for i in range(100):
                if task_future.done():
                    progress.update(task, completed=100)
                    break
                progress.update(task, advance=1)
                await asyncio.sleep(0.01)

            await task_future
            return result

    def format_response(self, response: str, language: Optional[str] = None):
        """Formatea respuesta con syntax highlighting"""
        if language:
            # Si es código, usar syntax highlighting
            syntax = Syntax(response, language, theme="monokai", line_numbers=True)
            self.console.print(Panel(syntax, title=f"[bold green]{language.upper()} Code[/bold green]"))
        else:
            # Si es markdown/texto, renderizar como markdown
            md = Markdown(response)
            self.console.print(Panel(md, title="[bold blue]Response[/bold blue]", border_style="blue"))

    def prompt_with_autocomplete(self, prompt: str, choices: List[str] = None) -> str:
        """Prompt con autocompletado"""
        if choices:
            self.console.print(f"[dim]Available: {', '.join(choices)}[/dim]")

        return Prompt.ask(f"[bold cyan]{prompt}[/bold cyan]")

    def confirm_action(self, message: str) -> bool:
        """Confirma una acción"""
        return Confirm.ask(f"[yellow]{message}[/yellow]")

    def show_error(self, error: str):
        """Muestra error formateado"""
        self.console.print(f"[bold red]❌ Error:[/bold red] {error}")

    def show_success(self, message: str):
        """Muestra mensaje de éxito"""
        self.console.print(f"[bold green]✅ Success:[/bold green] {message}")

    def show_warning(self, message: str):
        """Muestra advertencia"""
        self.console.print(f"[bold yellow]⚠️  Warning:[/bold yellow] {message}")

    def show_info(self, message: str):
        """Muestra información"""
        self.console.print(f"[bold blue]ℹ️  Info:[/bold blue] {message}")

    def create_tree(self, data: Dict, title: str = "Structure"):
        """Crea árbol visual de datos"""
        tree = Tree(f"[bold cyan]{title}[/bold cyan]")

        def add_items(node, items):
            if isinstance(items, dict):
                for key, value in items.items():
                    if isinstance(value, (dict, list)):
                        branch = node.add(f"[yellow]{key}[/yellow]")
                        add_items(branch, value)
                    else:
                        node.add(f"[green]{key}[/green]: {value}")
            elif isinstance(items, list):
                for item in items:
                    if isinstance(item, (dict, list)):
                        add_items(node, item)
                    else:
                        node.add(str(item))

        add_items(tree, data)
        return tree

    def show_metrics_dashboard(self, metrics: Dict):
        """Muestra dashboard de métricas"""
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="main"),
            Layout(name="footer", size=3)
        )

        layout["header"].update(Panel("[bold cyan]NubemSuperFClaude Metrics[/bold cyan]"))

        # Crear tabla de métricas
        metrics_table = Table(show_header=True, header_style="bold magenta")
        metrics_table.add_column("Metric", style="cyan")
        metrics_table.add_column("Value", style="green")
        metrics_table.add_column("Status", style="yellow")

        for key, value in metrics.items():
            status = "🟢" if value.get('healthy', True) else "🔴"
            metrics_table.add_row(
                key,
                str(value.get('value', 'N/A')),
                status
            )

        layout["main"].update(Panel(metrics_table))
        layout["footer"].update(Panel(f"[dim]Updated: {time.strftime('%Y-%m-%d %H:%M:%S')}[/dim]"))

        self.console.print(layout)

    def interactive_menu(self, options: List[str], title: str = "Select an option") -> int:
        """Menú interactivo"""
        self.console.print(f"\n[bold cyan]{title}:[/bold cyan]")

        for i, option in enumerate(options, 1):
            self.console.print(f"  [cyan]{i}.[/cyan] {option}")

        while True:
            try:
                choice = Prompt.ask("\n[bold]Enter choice[/bold]", default="1")
                choice_int = int(choice)
                if 1 <= choice_int <= len(options):
                    return choice_int - 1
                else:
                    self.show_error(f"Please enter a number between 1 and {len(options)}")
            except ValueError:
                self.show_error("Please enter a valid number")

    def show_chat_interface(self):
        """Interface de chat mejorada"""
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="chat", ratio=8),
            Layout(name="input", size=3)
        )

        layout["header"].update(Panel("[bold cyan]NubemClaude Chat Interface[/bold cyan]"))
        layout["chat"].update(Panel("💬 Chat history will appear here..."))
        layout["input"].update(Panel("[dim]Type your message and press Enter[/dim]"))

        return layout


class RichProgressTracker:
    """Tracker de progreso para operaciones largas"""

    def __init__(self, console: Console = None):
        self.console = console or Console()
        self.tasks = {}

    def create_multi_progress(self, tasks_list: List[str]):
        """Crea progress bar para múltiples tareas"""
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            console=self.console
        ) as progress:

            # Crear tareas
            for task_name in tasks_list:
                self.tasks[task_name] = progress.add_task(
                    f"[cyan]{task_name}",
                    total=100
                )

            # Simular progreso
            for i in range(100):
                for task_id in self.tasks.values():
                    progress.update(task_id, advance=1)
                time.sleep(0.05)

            self.console.print("[bold green]✅ All tasks completed![/bold green]")


# Funciones helper para integración con nubemclaude
def format_code_response(code: str, language: str = "python"):
    """Formatea respuesta de código"""
    syntax = Syntax(code, language, theme="monokai", line_numbers=True)
    console.print(Panel(syntax, title=f"[bold green]{language.upper()}[/bold green]",
                       border_style="green"))

def format_markdown_response(text: str):
    """Formatea respuesta markdown"""
    md = Markdown(text)
    console.print(Panel(md, border_style="blue"))

def show_thinking_animation(message: str = "Thinking..."):
    """Animación mientras el modelo piensa"""
    with console.status(f"[bold cyan]{message}[/bold cyan]", spinner="dots"):
        time.sleep(2)  # Será reemplazado con la llamada real

def print_styled(text: str, style: str = "cyan"):
    """Imprime texto con estilo"""
    console.print(f"[{style}]{text}[/{style}]")


# Testing
if __name__ == "__main__":
    cli = RichCLI()

    # Banner
    cli.print_banner()

    # Ejemplo de personas
    personas = [
        {"id": "dev-001", "name": "Code Expert", "specialty": "Software Development", "score": 0.95},
        {"id": "data-002", "name": "Data Scientist", "specialty": "Machine Learning & Analytics", "score": 0.88},
        {"id": "sec-003", "name": "Security Pro", "specialty": "Cybersecurity & DevSecOps", "score": 0.92}
    ]
    cli.show_personas_table(personas)

    # Menú interactivo
    choice = cli.interactive_menu(
        ["Execute Query", "Show History", "Configure", "Exit"],
        "Main Menu"
    )

    # Respuesta formateada
    sample_code = """
def hello_world():
    print("Hello from NubemSuperFClaude!")
    return True
"""
    cli.format_response(sample_code, "python")

    # Métricas
    metrics = {
        "API Calls": {"value": 1234, "healthy": True},
        "Cache Hit Rate": {"value": "87%", "healthy": True},
        "Active Sessions": {"value": 42, "healthy": True},
        "Error Rate": {"value": "0.1%", "healthy": True}
    }
    cli.show_metrics_dashboard(metrics)