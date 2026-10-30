from __future__ import annotations

import re
import unittest

from documentos_empresa_app.qt_ui.dialogs.help_content import (
    DEFAULT_HELP_TOPIC_ID,
    HELP_TOPICS,
    HELP_TOPICS_BY_ID,
)

_INTERNAL_LINK_RE = re.compile(r'href="topic:([a-z0-9_]+)"')


class HelpContentTests(unittest.TestCase):
    """Protege o manual (F1) contra erros de digitacao - um link interno
    (href="topic:...") apontando pra um id que nao existe falharia em silencio na
    tela (HelpDialog.show_topic cai pro topico padrao sem avisar ninguem)."""

    def test_default_topic_exists(self) -> None:
        self.assertIn(DEFAULT_HELP_TOPIC_ID, HELP_TOPICS_BY_ID)

    def test_topic_ids_are_unique(self) -> None:
        ids = [topic.id for topic in HELP_TOPICS]
        self.assertEqual(len(ids), len(set(ids)))

    def test_every_topic_has_title_and_content(self) -> None:
        for topic in HELP_TOPICS:
            self.assertTrue(topic.title.strip(), f"topico {topic.id} sem titulo")
            self.assertTrue(topic.html.strip(), f"topico {topic.id} sem conteudo")

    def test_internal_links_point_to_existing_topics(self) -> None:
        for topic in HELP_TOPICS:
            for target in _INTERNAL_LINK_RE.findall(topic.html):
                self.assertIn(
                    target,
                    HELP_TOPICS_BY_ID,
                    f'topico "{topic.id}" linka para "topic:{target}", que nao existe',
                )


if __name__ == "__main__":
    unittest.main()
