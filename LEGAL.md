# Avid compatibility and licensing context

This is independently written integration source using the documented ManuScript and Sibelius Connect interfaces. It does not redistribute Sibelius, its bundled utils implementation, manuals, fonts, sounds, scores or reference PDFs. Calling a bundled API does not make that API implementation part of this repository. The generated plugin contains this project's own methods.

Avid explicitly introduced Sibelius Connect for third-party remote-control integrations and directs developers to the ManuScript reference:

- [Avid: What's New in Sibelius March 2024](https://www.avid.com/resource-center/whats-new-in-sibelius-march-2024)
- [Avid: ManuScript Language Guide](https://resources.avid.com/SupportFiles/Sibelius/2024.6/ManuScript_Language_Guide.pdf)

However, Avid's [End User License Terms](https://www.avid.com/legal/end-user-license-terms), revised July 23, 2026, contain an API restriction except as provided in the agreement. The relationship between that broad clause and the published integration documentation has not been confirmed in writing for this project. Documentation and existing integrations support the intended interoperability use; they are not project-specific approval or a guarantee against an objection.

There is an established source-distribution precedent: MakeMusic's [Dolet for Sibelius](https://github.com/MakeMusicInc/DoletSibelius) publishes ManuScript source under MIT and is also [listed in Avid's plugin directory](https://www.sibelius.com/download/plugins/index.html?category=4_1_1_1_1_1_1_1_1&versionname=16). This supports GitHub plus optional directory distribution as an existing practice; it does not establish project-specific API permission for this bridge.

Avid's [plugin directory](https://www.sibelius.com/download/plugins/index.html) describes listed third-party plugins as independently provided and disclaims responsibility for their licensing and operation. A directory listing should not be represented as legal clearance or Avid authorship. This project has not been submitted to or approved for that directory.

The MIT license covers the original project code only. Users must obtain their own Sibelius license, comply with applicable Avid terms, and have the necessary rights to any scores they process or share. Avid, Sibelius, Codex and OpenAI names identify compatibility or clients; no trademark license or endorsement is granted.
