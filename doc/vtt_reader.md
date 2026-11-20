# WebVTT Reader

## Overview

The WebVTT reader (`ttconv/vtt/reader.py`) converts a
[WebVTT](https://www.w3.org/TR/webvtt1/) document into a [data model](./data_model.md) document.

## Usage

```python
import ttconv.vtt.reader as vtt_reader

with open("captions.vtt", encoding="utf-8") as f:
  doc = vtt_reader.to_model(f)
```

`to_model` returns `None` if the document does not start with the WebVTT signature.

## STYLE blocks

The declarations of the `STYLE` blocks of the document are applied to the cue text, following the
WebVTT cascade:

* declarations marked `!important` win over normal declarations;
* otherwise, the declaration with the highest specificity wins, where `::cue` and the tag of its
  argument each count as a type selector, and classes and the `voice` attribute selector each count
  as a class selector;
* declarations with the same importance and specificity are resolved by their position in the file.

The presentational hints imposed by the cue text markup (e.g. `<b>` for bold, `<c.yellow>` for the
yellow default color) have a lower priority than any declaration of a `STYLE` block, like in a user
agent.

The supported selectors are `::cue`, `::cue(<tag>)`, `::cue(<classes>)`,
`::cue(<tag>.<classes>)` and `::cue(v[voice=<voice>])`, where `<tag>` is one of the cue text tags
(`b`, `c`, `i`, `lang`, `rb`, `rbc`, `rp`, `rt`, `rtc`, `ruby`, `u` and `v`). Selectors that apply
to the originating media element (e.g. `video::cue`) and ID selectors are not supported, since the
data model does not represent the originating element or cue identifiers.

Supported declarations are those whose value maps to a style property of the data model:
`color`, `background-color` (and `background` when it only consists of a color), `font-family`,
`font-size`, `font-style`, `font-weight`, `line-height`, `text-decoration`,
`text-combine-upright`, `ruby-position`, `ruby-align`, `opacity`, `visibility`, `white-space`,
`direction`, `unicode-bidi` and `display`.

Rules and declarations that are not supported are logged and ignored. They never prevent the
document from being read, and the cue text and its temporal properties are never modified. A
document without a `STYLE` block is read exactly as before.

Per the WebVTT specification, `STYLE` blocks are only recognised before the first cue, and a block
that contains a cue timing is not a style block.
