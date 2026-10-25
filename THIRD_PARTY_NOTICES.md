# Third-party software

The MIT license in `LICENSE` covers SpecHelper's own code and documentation.
Dependencies and external services retain their respective licenses and terms.
The source repository does not vendor installed packages or their binaries.
The lock files record dependency versions; they do not relicense dependencies.

## Dependencies with separate distribution obligations

| Component | License / scope |
|---|---|
| pglast | GPL-3.0-or-later; used by the backend to validate PostgreSQL queries. See its [source and license](https://github.com/lelit/pglast). |
| psycopg / psycopg-binary | LGPL-3.0-only; PostgreSQL adapter and binary distribution. See [upstream license](https://github.com/psycopg/psycopg/blob/master/LICENSE.txt). |
| lightningcss | MPL-2.0; frontend build dependency. |
| sharp / libvips optional native packages | Multiple upstream licenses, including LGPL; consult the [sharp-libvips licensing table](https://github.com/lovell/sharp-libvips). |
| caniuse-lite | CC-BY-4.0; browser compatibility data. |
| class-variance-authority | Apache-2.0. |
| Lucide / Feather | ISC / MIT; icon artwork and implementation retain upstream notices. |
| PyYAML | MIT; parses remote issue-form metadata with the safe loader. See the [upstream license](https://github.com/yaml/pyyaml/blob/main/LICENSE). |
| react-markdown / remark-gfm | MIT; render the Markdown publication preview. Preserve their notices when distributing installed packages. |

Other dependencies include software under MIT, BSD, Apache and PostgreSQL
licenses. Preserve the licenses and notices supplied with installed packages.
Built containers include dependencies and operating system packages; they must
not be represented as licensed exclusively under MIT. Distribution of a combined
backend including GPL components must also respect those components' licenses.

Codex CLI, Claude Code, Antigravity CLI and GitHub CLI are installed from upstream by the Dockerfiles.
Their licenses and the providers' account/service terms apply independently.
SpecHelper does not grant rights to their brands, credentials, or services.
Antigravity uses exact official Linux archives and SHA-512 values recorded in
`runtime/antigravity-release.json`; no native binary is vendored in this repository.
Its binary/service is not relicensed under MIT. Antigravity identification uses a
neutral bundled Lucide icon alongside the provider name, without a vendor logo claim.

## Adapted shadcn/ui components

The components in `frontend/src/components/ui/` follow and adapt shadcn/ui
patterns. The original notice is retained below.

MIT License

Copyright (c) 2023 shadcn

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

## Provider identification artwork

The small provider marks in `assistant-logo.tsx` identify the assistant actually
used for a task. The OpenAI Blossom is from the official
[OpenAI logo archive](https://cdn.openai.com/brand/OpenAI-Logos-2025.zip), subject
to [OpenAI brand guidelines](https://openai.com/brand/). The Claude symbol is from
[Claude's official site icon](https://claude.ai/favicon.svg). These marks belong
to OpenAI and Anthropic respectively; they are not covered by SpecHelper's MIT
license and do not imply endorsement. Artwork is bundled locally; viewing a queue
does not request assets from either provider.

GitHub and GitLab identification uses the locally bundled Lucide icons under
Lucide's ISC license. Jira, GLPI and unknown platforms use a neutral ticket icon
beside their visible platform name when no redistributable provider artwork is
bundled. No external image request or third-party logo download is needed.
