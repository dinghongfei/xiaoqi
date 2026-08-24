"""Host CLI commands (serve / preview-http)."""

import argparse

from bot.cli import build_parser


def _subcommand_names(parser: argparse.ArgumentParser) -> set[str]:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return set(action.choices)
    return set()


def test_parser_exposes_host_commands():
    names = _subcommand_names(build_parser())
    assert names == {"serve", "preview-http"}
