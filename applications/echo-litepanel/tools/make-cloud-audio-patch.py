#!/usr/bin/env python3
"""Produce a reviewable LitePanel host patch; never writes to its source tree."""
import argparse
import difflib
from pathlib import Path

CHANGES = {
    'connections.py': [
        ('if self.config["kind"] == "wifi":\n                            self.audio_in.append',
         'if self.config["kind"] in ("wifi", "mqtt"):\n                            self.audio_in.append'),
        ("if self.config['kind'] != 'wifi' or not self.connected:",
         "if self.config['kind'] not in ('wifi', 'mqtt') or not self.connected:")],
    'server.py': [
        ("session and session.config['kind'] == 'wifi' else []",
         "session and session.config['kind'] in ('wifi', 'mqtt') else []"),
        ("if MANAGER.kind != 'wifi' or not MANAGER.session:",
         "if MANAGER.kind not in ('wifi', 'mqtt') or not MANAGER.session:"),
        ("and MANAGER.kind != 'wifi':",
         "and MANAGER.kind not in ('wifi', 'mqtt'):")],
    'web/voice.js': [
        ("state.connection?.kind !== 'wifi'", "!['wifi', 'mqtt'].includes(state.connection?.kind)")]
}


def build_patch(source):
    output = []
    for prefix in ('', 'projects/litepanel/上位机/'):
        if not (source / prefix / 'connections.py').exists():
            continue
        for relative, changes in CHANGES.items():
            path = source / prefix / relative
            before = path.read_text(encoding='utf-8')
            after = before
            for old, new in changes:
                if after.count(old) != 1:
                    raise ValueError(f'{path}: source has changed; inspect {old!r}')
                after = after.replace(old, new)
            output.extend(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                                              fromfile='a/' + prefix + relative, tofile='b/' + prefix + relative))
    if not output:
        raise ValueError('LitePanel source not found')
    return ''.join(output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('litepanel_source', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    args.output.write_text(build_patch(args.litepanel_source), encoding='utf-8')
