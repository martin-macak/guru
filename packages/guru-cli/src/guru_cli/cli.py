import click


@click.group()
@click.version_option()
def cli():
    """Guru CLI."""


@cli.command()
def hello():
    """Say hello."""
    click.echo("Hello from guru-cli!")
