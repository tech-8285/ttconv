#!/usr/bin/env python
# -*- coding: UTF-8 -*-

# Copyright (c) 2022, Sandflow Consulting LLC
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice, this
#    list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR
# ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
# (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
# ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

"""WebVTT style sheet

This module implements the subset of CSS that is allowed in WebVTT STYLE blocks,
i.e. rules whose selector is based on the `::cue` pseudo-element.

The cascade is resolved the same way it is by a WebVTT user agent:

1. declarations marked `!important` win over normal declarations;
2. otherwise, the declaration with the highest specificity wins, where the
   `::cue` pseudo-element and the tag of its argument each count as a type
   selector, and classes and the `voice` attribute selector each count as a
   class selector;
3. declarations with the same importance and specificity are ordered by their
   position in the file, the last one winning.

Rules and declarations that cannot be supported by the data model are logged
and ignored; they never prevent the document from being read.
"""

from __future__ import annotations

import dataclasses
import logging
import re
import typing

import ttconv.style_properties as styles
import ttconv.utils as utils

LOGGER = logging.getLogger(__name__)

#: tags that may appear in the argument of a `::cue` selector
_CUE_TAGS = frozenset((
  "b", "c", "i", "lang", "rb", "rbc", "rp", "rt", "rtc", "ruby", "u", "v"
))

_SELECTOR_RE = re.compile(r"(?P<prefix>.*?)::cue(?:\((?P<arg>[^()]*)\))?", re.DOTALL)
_TAG_RE = re.compile(r"[a-zA-Z][\w-]*")
_CLASS_RE = re.compile(r"\.([\w-]+)")
_VOICE_ATTR_RE = re.compile(r"voice\s*=\s*(.+)", re.IGNORECASE)
_IMPORTANT_RE = re.compile(r"!\s*important\s*$", re.IGNORECASE)
_LENGTH_RE = re.compile(
  r"(?P<value>[+-]?(?:\d+(?:\.\d*)?|\.\d+))(?P<units>px|em|%|pt)",
  re.IGNORECASE
)
_NUMBER_RE = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)")


@dataclasses.dataclass(frozen=True)
class CueElement:
  """Describes an element of the cue tree, for the purpose of selector matching.

  `tag` is the name of the cue text tag that created the element, or `None` for
  the anonymous elements that contain text nodes. `is_root` is true for the
  element that represents the cue itself, which is matched by the `::cue`
  selector; the class selector of `::cue(...)` never matches it, per the WebVTT
  specification.
  """

  tag: typing.Optional[str] = None
  classes: typing.Tuple[str, ...] = ()
  voice: typing.Optional[str] = None
  is_root: bool = False


@dataclasses.dataclass(frozen=True)
class _Selector:
  """A `::cue` selector"""

  tag: typing.Optional[str]
  classes: typing.Tuple[str, ...]
  voice: typing.Optional[str]
  is_global: bool

  @property
  def specificity(self) -> typing.Tuple[int, int]:
    """CSS specificity of the selector, as (class count, type count)"""
    return (
      len(self.classes) + (1 if self.voice is not None else 0),
      1 + (1 if self.tag is not None else 0)
    )

  def matches(self, element: CueElement) -> bool:
    """Whether the selector matches `element`"""

    if self.tag is not None:
      if element.tag != self.tag:
        return False
    elif self.is_global:
      # `::cue` only matches the cue root element
      return element.is_root and element.tag is None

    if len(self.classes) > 0:

      # the class selector of `::cue(...)` does not match the cue root element
      if element.is_root:
        return False

      if not set(self.classes).issubset(element.classes):
        return False

    if self.voice is not None and element.voice != self.voice:
      return False

    return True


@dataclasses.dataclass(frozen=True)
class _Declaration:
  """A supported declaration"""

  style_prop: typing.Type[styles.StyleProperty]
  value: typing.Any
  important: bool


@dataclasses.dataclass(frozen=True)
class _Rule:
  """A parsed style rule"""

  selectors: typing.Tuple[_Selector, ...]
  declarations: typing.Tuple[_Declaration, ...]
  index: int


def _strip_comments(css: str) -> str:
  """Replaces CSS comments with a space"""

  result = []
  index = 0

  while index < len(css):

    if css.startswith("/*", index):
      end = css.find("*/", index + 2)
      if end < 0:
        LOGGER.warning("Ignoring unterminated CSS comment")
        break
      index = end + 2
      result.append(" ")
      continue

    result.append(css[index])
    index += 1

  return "".join(result)


def _find_block_end(css: str, open_index: int) -> int:
  """Returns the index of the `}` matching the `{` at `open_index`, or -1"""

  depth = 0
  quote = None
  index = open_index

  while index < len(css):

    char = css[index]

    if quote is not None:
      if char == "\\":
        index += 2
        continue
      if char == quote:
        quote = None
    elif char in ("\"", "'"):
      quote = char
    elif char == "{":
      depth += 1
    elif char == "}":
      depth -= 1
      if depth == 0:
        return index

    index += 1

  return -1


def _split_top_level(text: str, separator: str) -> typing.List[str]:
  """Splits `text` on `separator`, ignoring separators within strings, parentheses
  and square brackets."""

  parts = []
  buffer = []
  depth = 0
  quote = None
  index = 0

  while index < len(text):

    char = text[index]

    if quote is not None:
      buffer.append(char)
      if char == "\\" and index + 1 < len(text):
        buffer.append(text[index + 1])
        index += 2
        continue
      if char == quote:
        quote = None
    elif char in ("\"", "'"):
      quote = char
      buffer.append(char)
    elif char in ("(", "["):
      depth += 1
      buffer.append(char)
    elif char in (")", "]"):
      depth = max(0, depth - 1)
      buffer.append(char)
    elif char == separator and depth == 0:
      parts.append("".join(buffer))
      buffer = []
    else:
      buffer.append(char)

    index += 1

  parts.append("".join(buffer))

  return parts


def _parse_selector_argument(argument: str) -> typing.Optional[typing.Tuple[
    typing.Optional[str], typing.Tuple[str, ...], typing.Optional[str]]]:
  """Parses the argument of a `::cue(...)` selector.

  Returns `(tag, classes, voice)` or `None` if the argument is not supported.
  """

  text = argument.strip()

  if len(text) == 0:
    return None

  index = 0
  tag = None
  classes: typing.List[str] = []
  voice = None

  match = _TAG_RE.match(text)

  if match is not None:
    tag = match.group(0).lower()
    index = match.end()

    if tag not in _CUE_TAGS:
      return None

  while index < len(text) and text[index] == ".":
    match = _CLASS_RE.match(text, index)
    if match is None:
      return None
    classes.append(match.group(1))
    index = match.end()

  if index < len(text) and text[index] == "[":
    end = text.find("]", index)
    if end < 0:
      return None
    match = _VOICE_ATTR_RE.fullmatch(text[index + 1:end].strip())
    if match is None:
      return None

    voice = match.group(1).strip()

    if len(voice) >= 2 and voice[0] == voice[-1] and voice[0] in ("\"", "'"):
      voice = voice[1:-1]

    if len(voice) == 0:
      return None

    index = end + 1

  if index != len(text):
    return None

  if tag is None and len(classes) == 0 and voice is None:
    return None

  return tag, tuple(classes), voice


def _parse_selector(selector: str) -> typing.Optional[_Selector]:
  """Parses a single selector. Returns `None` if it is not supported."""

  match = _SELECTOR_RE.fullmatch(selector.strip())

  if match is None:
    LOGGER.warning("Ignoring unsupported WebVTT style selector '%s'", selector.strip())
    return None

  prefix = match.group("prefix").strip()

  # the selector may be prefixed by `*`, e.g. `*::cue(b)`; any other prefix
  # applies to the originating element, which the data model does not represent
  if prefix not in ("", "*"):
    LOGGER.warning(
      "Ignoring WebVTT style selector '%s': selectors on the originating element are not supported",
      selector.strip()
    )
    return None

  argument = match.group("arg")

  if argument is None:
    return _Selector(tag=None, classes=(), voice=None, is_global=True)

  parsed_argument = _parse_selector_argument(argument)

  if parsed_argument is None:
    LOGGER.warning(
      "Ignoring WebVTT style selector '%s': unsupported ::cue argument",
      selector.strip()
    )
    return None

  tag, classes, voice = parsed_argument

  return _Selector(tag=tag, classes=classes, voice=voice, is_global=False)


def _parse_length(value: str) -> typing.Optional[styles.LengthType]:
  """Parses a CSS length, mapping it to a data model length"""

  if value.strip() == "0":
    return styles.LengthType(0, styles.LengthType.Units.px)

  match = _LENGTH_RE.fullmatch(value.strip())

  if match is None:
    return None

  number = float(match.group("value"))
  units = match.group("units").lower()

  if units == "%":
    return styles.LengthType(number, styles.LengthType.Units.pct)

  if units == "em":
    return styles.LengthType(number, styles.LengthType.Units.em)

  if units == "pt":
    # 1pt = 4/3 px
    return styles.LengthType(number * 4 / 3, styles.LengthType.Units.px)

  return styles.LengthType(number, styles.LengthType.Units.px)


def _parse_color(value: str) -> typing.Optional[styles.ColorType]:
  """Parses a CSS color"""

  try:
    return utils.parse_color(value.strip())
  except (TypeError, ValueError):
    return None


def _parse_font_family(value: str) -> typing.Tuple[typing.Union[str, styles.GenericFontFamilyType], ...]:
  """Parses a CSS font family list"""

  generic_families = {
    "sans-serif": styles.GenericFontFamilyType.sansSerif,
    "serif": styles.GenericFontFamilyType.serif,
    "monospace": styles.GenericFontFamilyType.monospace,
    "cursive": styles.GenericFontFamilyType.proportionalSansSerif,
    "fantasy": styles.GenericFontFamilyType.proportionalSerif,
    "system-ui": styles.GenericFontFamilyType.sansSerif,
  }

  families = []

  for family in value.split(","):

    family = family.strip()

    if len(family) >= 2 and family[0] == family[-1] and family[0] in ("\"", "'"):
      family = family[1:-1]

    if len(family) == 0:
      continue

    families.append(generic_families.get(family.lower(), family))

  return tuple(families)


def _parse_font_weight(value: str) -> typing.Optional[styles.FontWeightType]:
  """Parses a CSS font weight"""

  keyword = value.strip().lower()

  if keyword == "normal":
    return styles.FontWeightType.normal

  if keyword == "bold":
    return styles.FontWeightType.bold

  if _NUMBER_RE.fullmatch(keyword):
    return styles.FontWeightType.bold if float(keyword) >= 600 else styles.FontWeightType.normal

  return None


def _parse_font_style(value: str) -> typing.Optional[styles.FontStyleType]:
  """Parses a CSS font style"""

  keyword = value.strip().lower()

  if keyword == "normal":
    return styles.FontStyleType.normal

  if keyword == "italic":
    return styles.FontStyleType.italic

  if keyword == "oblique":
    return styles.FontStyleType.oblique

  return None


def _parse_text_decoration(value: str) -> typing.Optional[styles.TextDecorationType]:
  """Parses a CSS text decoration"""

  tokens = value.lower().split()

  if not tokens:
    return None

  if "none" in tokens and len(tokens) > 1:
    return None

  underline = "underline" in tokens
  line_through = "line-through" in tokens
  overline = "overline" in tokens

  supported = {"none", "underline", "line-through", "overline"}

  if not all(token in supported for token in tokens) and not (underline or line_through or overline):
    return None

  if not (underline or line_through or overline) and "none" not in tokens:
    return None

  return styles.TextDecorationType(
    underline=underline,
    line_through=line_through,
    overline=overline
  )


def _parse_text_combine(value: str) -> typing.Optional[styles.TextCombineType]:
  """Parses a CSS text-combine-upright value"""

  keyword = value.strip().lower()

  if keyword == "none":
    return styles.TextCombineType.none

  if keyword == "all":
    return styles.TextCombineType.all

  return None


def _parse_ruby_position(value: str) -> typing.Optional[styles.AnnotationPositionType]:
  """Parses a CSS ruby-position value"""

  keyword = value.strip().lower()

  if keyword in ("over", "before"):
    return styles.AnnotationPositionType.before

  if keyword in ("under", "after"):
    return styles.AnnotationPositionType.after

  if keyword == "outside":
    return styles.AnnotationPositionType.outside

  return None


def _parse_ruby_align(value: str) -> typing.Optional[styles.RubyAlignType]:
  """Parses a CSS ruby-align value"""

  keyword = value.strip().lower()

  if keyword == "center":
    return styles.RubyAlignType.center

  if keyword in ("space-around", "space-between"):
    return styles.RubyAlignType.spaceAround

  return None


def _parse_direction(value: str) -> typing.Optional[styles.DirectionType]:
  """Parses a CSS direction value"""

  keyword = value.strip().lower()

  if keyword == "ltr":
    return styles.DirectionType.ltr

  if keyword == "rtl":
    return styles.DirectionType.rtl

  return None


def _parse_unicode_bidi(value: str) -> typing.Optional[styles.UnicodeBidiType]:
  """Parses a CSS unicode-bidi value"""

  keyword = value.strip().lower()

  if keyword == "normal":
    return styles.UnicodeBidiType.normal

  if keyword == "embed":
    return styles.UnicodeBidiType.embed

  if keyword == "bidi-override":
    return styles.UnicodeBidiType.bidiOverride

  return None


def _parse_visibility(value: str) -> typing.Optional[styles.VisibilityType]:
  """Parses a CSS visibility value"""

  keyword = value.strip().lower()

  if keyword == "visible":
    return styles.VisibilityType.visible

  if keyword == "hidden":
    return styles.VisibilityType.hidden

  return None


def _parse_white_space(value: str) -> typing.Optional[styles.WrapOptionType]:
  """Parses a CSS white-space value"""

  keyword = value.strip().lower()

  if keyword in ("nowrap", "pre"):
    return styles.WrapOptionType.noWrap

  if keyword in ("normal", "pre-wrap", "pre-line", "break-spaces"):
    return styles.WrapOptionType.wrap

  return None


def _parse_line_height(value: str) -> typing.Optional[typing.Any]:
  """Parses a CSS line height"""

  keyword = value.strip().lower()

  if keyword == "normal":
    return styles.SpecialValues.normal

  if _NUMBER_RE.fullmatch(keyword):
    return styles.LengthType(float(keyword) * 100, styles.LengthType.Units.pct)

  return _parse_length(value)


def _parse_background(value: str) -> typing.Optional[styles.ColorType]:
  """Parses a CSS background shorthand that only consists of a color"""

  keyword = value.strip().lower()

  if keyword == "none":
    return styles.NamedColors.transparent.value

  if len(_split_top_level(value, " ")) > 1:
    return None

  return _parse_color(value)


def _parse_static_value(
    name: str,
    value: str
  ) -> typing.Optional[typing.Tuple[typing.Type[styles.StyleProperty], typing.Any]]:
  """Parses a supported declaration value; returns None if unsupported"""

  if name == "color":
    parsed = _parse_color(value)
    return (styles.StyleProperties.Color, parsed) if parsed is not None else None

  if name == "background-color":
    parsed = _parse_color(value)
    return (styles.StyleProperties.BackgroundColor, parsed) if parsed is not None else None

  if name == "background":
    parsed = _parse_background(value)
    return (styles.StyleProperties.BackgroundColor, parsed) if parsed is not None else None

  if name == "font-family":
    families = _parse_font_family(value)
    return (styles.StyleProperties.FontFamily, families) if len(families) > 0 else None

  if name == "font-size":
    parsed = _parse_length(value)
    return (styles.StyleProperties.FontSize, parsed) if parsed is not None else None

  if name == "font-style":
    parsed = _parse_font_style(value)
    return (styles.StyleProperties.FontStyle, parsed) if parsed is not None else None

  if name == "font-weight":
    parsed = _parse_font_weight(value)
    return (styles.StyleProperties.FontWeight, parsed) if parsed is not None else None

  if name in ("text-decoration", "text-decoration-line"):
    parsed = _parse_text_decoration(value)
    return (styles.StyleProperties.TextDecoration, parsed) if parsed is not None else None

  if name == "text-combine-upright":
    parsed = _parse_text_combine(value)
    return (styles.StyleProperties.TextCombine, parsed) if parsed is not None else None

  if name == "line-height":
    parsed = _parse_line_height(value)
    return (styles.StyleProperties.LineHeight, parsed) if parsed is not None else None

  if name == "opacity":
    if not _NUMBER_RE.fullmatch(value.strip()):
      return None
    return (styles.StyleProperties.Opacity, float(value.strip()))

  if name == "visibility":
    parsed = _parse_visibility(value)
    return (styles.StyleProperties.Visibility, parsed) if parsed is not None else None

  if name == "white-space":
    parsed = _parse_white_space(value)
    return (styles.StyleProperties.WrapOption, parsed) if parsed is not None else None

  if name == "direction":
    parsed = _parse_direction(value)
    return (styles.StyleProperties.Direction, parsed) if parsed is not None else None

  if name == "unicode-bidi":
    parsed = _parse_unicode_bidi(value)
    return (styles.StyleProperties.UnicodeBidi, parsed) if parsed is not None else None

  if name == "ruby-position":
    parsed = _parse_ruby_position(value)
    return (styles.StyleProperties.RubyPosition, parsed) if parsed is not None else None

  if name == "ruby-align":
    parsed = _parse_ruby_align(value)
    return (styles.StyleProperties.RubyAlign, parsed) if parsed is not None else None

  if name == "display":
    keyword = value.strip().lower()
    if keyword == "none":
      return (styles.StyleProperties.Display, styles.DisplayType.none)
    if keyword in ("auto", "inline", "block", "inline-block", "contents"):
      return (styles.StyleProperties.Display, styles.DisplayType.auto)
    return None

  return None


def _parse_declarations(body: str) -> typing.Tuple[_Declaration, ...]:
  """Parses the declaration block of a rule, ignoring unsupported declarations"""

  declarations = []

  for declaration in _split_top_level(body, ";"):

    declaration = declaration.strip()

    if len(declaration) == 0:
      continue

    if ":" not in declaration:
      LOGGER.warning("Ignoring malformed WebVTT style declaration '%s'", declaration)
      continue

    name, value = declaration.split(":", 1)
    name = name.strip().lower()
    value = value.strip()

    important = False
    match = _IMPORTANT_RE.search(value)

    if match is not None:
      important = True
      value = value[:match.start()].strip()

    parsed = _parse_static_value(name, value)

    if parsed is None:
      LOGGER.warning(
        "Ignoring unsupported WebVTT style declaration '%s: %s'",
        name,
        value
      )
      continue

    style_prop, style_value = parsed

    declarations.append(_Declaration(style_prop, style_value, important))

  return tuple(declarations)


class VttStyleSheet:
  """Collection of the style rules found in the STYLE blocks of a WebVTT document.

  Unsupported rules and declarations are logged and ignored.
  """

  def __init__(self) -> None:
    self._rules: typing.List[_Rule] = []

  def __len__(self) -> int:
    return len(self._rules)

  def is_empty(self) -> bool:
    """Whether the style sheet contains no rule"""
    return len(self._rules) == 0

  def add_style_block(self, lines: typing.Sequence[str], line_number: typing.Optional[int] = None) -> None:
    """Parses and adds the content of a WebVTT style block.

    A style block that contains a cue timing (`-->`) is invalid per the WebVTT
    specification and is ignored.
    """

    css = "\n".join(lines)

    if "-->" in css:
      LOGGER.warning(
        "Ignoring invalid WebVTT style block%s: it contains a cue timing",
        "" if line_number is None else f" at line {line_number}"
      )
      return

    self.add_css(css, line_number)

  def add_css(self, css: str, line_number: typing.Optional[int] = None) -> None:
    """Parses and adds CSS rules"""

    location = "" if line_number is None else f" at line {line_number}"

    for kind, *parts in self._iter_rules(_strip_comments(css)):

      if kind == "at":
        LOGGER.warning(
          "Ignoring unsupported WebVTT style at-rule '%s'%s",
          parts[0],
          location
        )
        continue

      prelude, body = parts

      selectors = tuple(
        selector
        for selector in (
          _parse_selector(item) for item in _split_top_level(prelude, ",")
        )
        if selector is not None
      )

      if len(selectors) == 0:
        LOGGER.warning("Ignoring WebVTT style rule without a supported selector%s", location)
        continue

      declarations = _parse_declarations(body)

      if len(declarations) == 0:
        LOGGER.warning("Ignoring WebVTT style rule without a supported declaration%s", location)
        continue

      self._rules.append(_Rule(selectors, declarations, len(self._rules)))

  @staticmethod
  def _iter_rules(css: str) -> typing.Iterator[typing.Tuple]:
    """Iterates over the rules of a style sheet, yielding either
    `("at", prelude)` or `("style", prelude, body)`."""

    index = 0

    while index < len(css):

      while index < len(css) and css[index].isspace():
        index += 1

      if index >= len(css):
        break

      if css[index] == "}":
        LOGGER.warning("Ignoring unexpected '}' in WebVTT style block")
        index += 1
        continue

      if css[index] == "@":
        end = index

        while end < len(css) and css[end] not in ("{", ";"):
          end += 1

        prelude = css[index:end].strip()

        if end < len(css) and css[end] == "{":
          block_end = _find_block_end(css, end)
          if block_end < 0:
            LOGGER.warning("Ignoring unterminated WebVTT style at-rule '%s'", prelude)
            yield ("at", prelude)
            return
          yield ("at", prelude)
          index = block_end + 1
        else:
          yield ("at", prelude)
          index = end + 1

        continue

      open_index = css.find("{", index)

      if open_index < 0:
        if len(css[index:].strip()) > 0:
          LOGGER.warning("Ignoring trailing text in WebVTT style block: '%s'", css[index:].strip())
        return

      prelude = css[index:open_index].strip()
      block_end = _find_block_end(css, open_index)

      if block_end < 0:
        LOGGER.warning("Ignoring unterminated WebVTT style rule '%s'", prelude)
        return

      yield ("style", prelude, css[open_index + 1:block_end])

      index = block_end + 1

  def get_style_values(
      self,
      element: CueElement
    ) -> typing.List[typing.Tuple[typing.Type[styles.StyleProperty], typing.Any, bool, typing.Tuple[int, int]]]:
    """Returns the cascaded style values that apply to `element`.

    The result is a list of `(style property, value, important, specificity)`
    tuples, ordered from the highest to the lowest priority. Earlier entries
    therefore override later ones."""

    matches = []

    for rule in self._rules:

      specificities = [
        selector.specificity
        for selector in rule.selectors
        if selector.matches(element)
      ]

      if len(specificities) == 0:
        continue

      specificity = max(specificities)

      for declaration_index, declaration in enumerate(rule.declarations):
        matches.append((
          # sort key: important, class count, type count, rule order, declaration order
          declaration.important,
          specificity[0],
          specificity[1],
          rule.index,
          declaration_index,
          declaration
        ))

    matches.sort(key=lambda item: item[:5], reverse=True)

    values = {}

    for match in matches:
      declaration = match[5]
      if declaration.style_prop not in values:
        values[declaration.style_prop] = (
          declaration.value,
          declaration.important,
          (match[1], match[2])
        )

    return [
      (style_prop, value, important, specificity)
      for style_prop, (value, important, specificity) in values.items()
    ]
