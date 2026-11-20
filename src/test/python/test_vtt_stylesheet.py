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

"""Unit tests for the WebVTT style sheet"""

# pylint: disable=R0201,C0115,C0116,W0212

import unittest

import ttconv.style_properties as styles
from ttconv.vtt.stylesheet import CueElement, VttStyleSheet


def _values(stylesheet: VttStyleSheet, element: CueElement) -> dict:
  return {
    style_prop: value
    for style_prop, value, _important, _specificity in stylesheet.get_style_values(element)
  }


class VttStyleSheetTest(unittest.TestCase):

  def test_global_rule(self):
    stylesheet = VttStyleSheet()
    stylesheet.add_css("::cue { color: lime; }")

    self.assertEqual(
      {styles.StyleProperties.Color: styles.NamedColors.lime.value},
      _values(stylesheet, CueElement(is_root=True))
    )

    # `::cue` does not match the elements inside the cue
    self.assertEqual({}, _values(stylesheet, CueElement(tag="b")))

  def test_empty_stylesheet(self):
    stylesheet = VttStyleSheet()
    self.assertTrue(stylesheet.is_empty())
    self.assertEqual(0, len(stylesheet))
    self.assertEqual({}, _values(stylesheet, CueElement(is_root=True)))

  def test_tag_selector(self):
    stylesheet = VttStyleSheet()
    stylesheet.add_css("::cue(b) { color: red; }")

    self.assertEqual(
      {styles.StyleProperties.Color: styles.NamedColors.red.value},
      _values(stylesheet, CueElement(tag="b"))
    )
    self.assertEqual({}, _values(stylesheet, CueElement(tag="i")))

  def test_class_selector(self):
    stylesheet = VttStyleSheet()
    stylesheet.add_css("::cue(.loud) { font-size: 2em; }")

    self.assertEqual(
      {styles.StyleProperties.FontSize: styles.LengthType(2, styles.LengthType.Units.em)},
      _values(stylesheet, CueElement(tag="c", classes=("loud",)))
    )
    self.assertEqual({}, _values(stylesheet, CueElement(tag="c", classes=("quiet",))))

    # the class selector does not match the cue root
    self.assertEqual({}, _values(stylesheet, CueElement(is_root=True)))

  def test_voice_selector(self):
    stylesheet = VttStyleSheet()
    stylesheet.add_css('::cue(v[voice="Mary"]) { color: cyan; }')

    self.assertEqual(
      {styles.StyleProperties.Color: styles.NamedColors.cyan.value},
      _values(stylesheet, CueElement(tag="v", voice="Mary"))
    )
    self.assertEqual({}, _values(stylesheet, CueElement(tag="v", voice="Esme")))

  def test_tag_and_class_selector(self):
    stylesheet = VttStyleSheet()
    stylesheet.add_css("::cue(c.loud) { color: yellow; }")

    self.assertEqual(
      {styles.StyleProperties.Color: styles.NamedColors.yellow.value},
      _values(stylesheet, CueElement(tag="c", classes=("loud",)))
    )
    self.assertEqual({}, _values(stylesheet, CueElement(tag="i", classes=("loud",))))

  def test_specificity(self):
    stylesheet = VttStyleSheet()
    stylesheet.add_css("::cue { color: lime; }")
    stylesheet.add_css("::cue(b) { color: red; }")
    stylesheet.add_css("::cue(b.loud) { color: yellow; }")

    self.assertEqual(
      {styles.StyleProperties.Color: styles.NamedColors.yellow.value},
      _values(stylesheet, CueElement(tag="b", classes=("loud",)))
    )

    self.assertEqual(
      {styles.StyleProperties.Color: styles.NamedColors.red.value},
      _values(stylesheet, CueElement(tag="b"))
    )

  def test_document_order(self):
    stylesheet = VttStyleSheet()
    stylesheet.add_css("::cue { color: lime; }")
    stylesheet.add_css("::cue { color: red; }")

    self.assertEqual(
      {styles.StyleProperties.Color: styles.NamedColors.red.value},
      _values(stylesheet, CueElement(is_root=True))
    )

  def test_important(self):
    stylesheet = VttStyleSheet()
    stylesheet.add_css("::cue(b.loud) { color: red !important; }")
    stylesheet.add_css("::cue { color: lime; }")

    self.assertEqual(
      {styles.StyleProperties.Color: styles.NamedColors.red.value},
      _values(stylesheet, CueElement(tag="b", classes=("loud",)))
    )

    # an `!important` declaration wins over a later normal declaration
    stylesheet = VttStyleSheet()
    stylesheet.add_css("::cue { color: lime !important; }")
    stylesheet.add_css("::cue { color: red; }")

    self.assertEqual(
      {styles.StyleProperties.Color: styles.NamedColors.lime.value},
      _values(stylesheet, CueElement(is_root=True))
    )

  def test_multiple_selectors(self):
    stylesheet = VttStyleSheet()
    stylesheet.add_css("::cue(b), ::cue(i) { color: red; }")

    self.assertEqual(
      {styles.StyleProperties.Color: styles.NamedColors.red.value},
      _values(stylesheet, CueElement(tag="b"))
    )
    self.assertEqual(
      {styles.StyleProperties.Color: styles.NamedColors.red.value},
      _values(stylesheet, CueElement(tag="i"))
    )

  def test_multiple_declarations(self):
    stylesheet = VttStyleSheet()
    stylesheet.add_css("::cue { color: lime; font-style: italic; }")

    self.assertEqual(
      {
        styles.StyleProperties.Color: styles.NamedColors.lime.value,
        styles.StyleProperties.FontStyle: styles.FontStyleType.italic
      },
      _values(stylesheet, CueElement(is_root=True))
    )

  def test_comments_are_ignored(self):
    stylesheet = VttStyleSheet()
    stylesheet.add_css("/* leading */ ::cue { /* inner */ color: lime; } /* trailing */")

    self.assertEqual(
      {styles.StyleProperties.Color: styles.NamedColors.lime.value},
      _values(stylesheet, CueElement(is_root=True))
    )

  def test_unsupported_selector_is_ignored(self):
    stylesheet = VttStyleSheet()
    stylesheet.add_css("video::cue { color: red; }")
    stylesheet.add_css("::cue(#foo) { color: red; }")
    stylesheet.add_css("::cue(v:hover) { color: red; }")
    stylesheet.add_css("i { color: red; }")

    self.assertTrue(stylesheet.is_empty())
    self.assertEqual({}, _values(stylesheet, CueElement(tag="i")))

  def test_universal_prefix_is_supported(self):
    stylesheet = VttStyleSheet()
    stylesheet.add_css("*::cue(b) { color: red; }")

    self.assertEqual(
      {styles.StyleProperties.Color: styles.NamedColors.red.value},
      _values(stylesheet, CueElement(tag="b"))
    )

  def test_unsupported_declarations_are_ignored(self):
    stylesheet = VttStyleSheet()
    stylesheet.add_css("::cue { color: lime; width: 20px; not-a-property: 1; }")

    self.assertEqual(
      {styles.StyleProperties.Color: styles.NamedColors.lime.value},
      _values(stylesheet, CueElement(is_root=True))
    )

  def test_rule_without_supported_declaration_is_ignored(self):
    stylesheet = VttStyleSheet()
    stylesheet.add_css("::cue { width: 20px; }")

    self.assertTrue(stylesheet.is_empty())

  def test_at_rules_are_ignored(self):
    stylesheet = VttStyleSheet()
    stylesheet.add_css('@import "style.css"; ::cue { color: lime; }')
    stylesheet.add_css("@media screen { ::cue { color: red; } }")

    self.assertEqual(
      {styles.StyleProperties.Color: styles.NamedColors.lime.value},
      _values(stylesheet, CueElement(is_root=True))
    )

  def test_malformed_rules_do_not_prevent_parsing(self):
    stylesheet = VttStyleSheet()
    stylesheet.add_css("::cue { color: lime; \n ::cue(b) { color: red; }")
    stylesheet.add_css("garbage without braces")
    stylesheet.add_css("::cue(i) { color: yellow; }")

    self.assertEqual(
      {styles.StyleProperties.Color: styles.NamedColors.yellow.value},
      _values(stylesheet, CueElement(tag="i"))
    )

  def test_style_block_with_cue_timing_is_ignored(self):
    stylesheet = VttStyleSheet()
    stylesheet.add_style_block(["::cue { color: lime; }", "00:00:00.000 --> 00:00:01.000"])

    self.assertTrue(stylesheet.is_empty())

  def test_multiple_style_blocks(self):
    stylesheet = VttStyleSheet()
    stylesheet.add_style_block(["::cue { color: lime; }"])
    stylesheet.add_style_block(["::cue { background-color: red; }"])

    self.assertEqual(
      {
        styles.StyleProperties.Color: styles.NamedColors.lime.value,
        styles.StyleProperties.BackgroundColor: styles.NamedColors.red.value
      },
      _values(stylesheet, CueElement(is_root=True))
    )

  def test_color_formats(self):
    stylesheet = VttStyleSheet()
    stylesheet.add_css("::cue { color: #ffff00ff; background-color: #000000ff; }")

    self.assertEqual(
      {
        styles.StyleProperties.Color: styles.ColorType((255, 255, 0, 255)),
        styles.StyleProperties.BackgroundColor: styles.ColorType((0, 0, 0, 255))
      },
      _values(stylesheet, CueElement(is_root=True))
    )

  def test_background_shorthand(self):
    stylesheet = VttStyleSheet()
    stylesheet.add_css("::cue { background: red; }")

    self.assertEqual(
      {styles.StyleProperties.BackgroundColor: styles.NamedColors.red.value},
      _values(stylesheet, CueElement(is_root=True))
    )

    # a shorthand with more than a color is not supported
    stylesheet = VttStyleSheet()
    stylesheet.add_css('::cue { background: url("background.png") red; }')

    self.assertTrue(stylesheet.is_empty())

  def test_unsupported_url_is_ignored(self):
    stylesheet = VttStyleSheet()
    stylesheet.add_css("::cue { background-image: url(support/background.png); color: lime; }")

    self.assertEqual(
      {styles.StyleProperties.Color: styles.NamedColors.lime.value},
      _values(stylesheet, CueElement(is_root=True))
    )

  def test_text_decoration(self):
    stylesheet = VttStyleSheet()
    stylesheet.add_css("::cue { text-decoration: underline; }")

    self.assertEqual(
      {
        styles.StyleProperties.TextDecoration: styles.TextDecorationType(
          underline=True,
          line_through=False,
          overline=False
        )
      },
      _values(stylesheet, CueElement(is_root=True))
    )

  def test_invalid_important(self):
    stylesheet = VttStyleSheet()
    stylesheet.add_css("::cue { color: not-a-color !important; }")

    self.assertTrue(stylesheet.is_empty())

  def _declaration(self, declaration: str):
    stylesheet = VttStyleSheet()
    stylesheet.add_css("::cue { " + declaration + " }")
    values = _values(stylesheet, CueElement(is_root=True))
    self.assertEqual(1, len(values), declaration)
    return next(iter(values.items()))

  def test_value_color(self):
    self.assertEqual(
      (styles.StyleProperties.Color, styles.NamedColors.red.value),
      self._declaration("color: red")
    )
    self.assertEqual(
      (styles.StyleProperties.Color, styles.ColorType((18, 52, 86, 255))),
      self._declaration("color: #123456")
    )
    self.assertEqual(
      (styles.StyleProperties.Color, styles.ColorType((18, 52, 86, 120))),
      self._declaration("color: #12345678")
    )
    self.assertEqual(
      (styles.StyleProperties.Color, styles.ColorType((1, 2, 3, 255))),
      self._declaration("color: rgb(1, 2, 3)")
    )

  def test_value_font_family(self):
    self.assertEqual(
      (styles.StyleProperties.FontFamily, (styles.GenericFontFamilyType.serif,)),
      self._declaration("font-family: serif")
    )
    self.assertEqual(
      (styles.StyleProperties.FontFamily, ("My Font", styles.GenericFontFamilyType.monospace)),
      self._declaration('font-family: "My Font", monospace')
    )
    self.assertEqual(
      (styles.StyleProperties.FontFamily, (styles.GenericFontFamilyType.sansSerif,)),
      self._declaration("font-family: sans-serif")
    )
    self.assertEqual(
      (styles.StyleProperties.FontFamily, (styles.GenericFontFamilyType.proportionalSansSerif,)),
      self._declaration("font-family: cursive")
    )
    self.assertEqual(
      (styles.StyleProperties.FontFamily, (styles.GenericFontFamilyType.proportionalSerif,)),
      self._declaration("font-family: fantasy")
    )
    self.assertEqual(
      (styles.StyleProperties.FontFamily, (styles.GenericFontFamilyType.sansSerif,)),
      self._declaration("font-family: system-ui")
    )

  def test_value_font_size(self):
    self.assertEqual(
      (styles.StyleProperties.FontSize, styles.LengthType(11, styles.LengthType.Units.px)),
      self._declaration("font-size: 11px")
    )
    self.assertEqual(
      (styles.StyleProperties.FontSize, styles.LengthType(50, styles.LengthType.Units.pct)),
      self._declaration("font-size: 50%")
    )
    self.assertEqual(
      (styles.StyleProperties.FontSize, styles.LengthType(4 / 3, styles.LengthType.Units.px)),
      self._declaration("font-size: 1pt")
    )
    self.assertEqual(
      (styles.StyleProperties.FontSize, styles.LengthType(0, styles.LengthType.Units.px)),
      self._declaration("font-size: 0")
    )

  def test_value_font_weight(self):
    self.assertEqual(
      (styles.StyleProperties.FontWeight, styles.FontWeightType.bold),
      self._declaration("font-weight: bold")
    )
    self.assertEqual(
      (styles.StyleProperties.FontWeight, styles.FontWeightType.normal),
      self._declaration("font-weight: normal")
    )
    self.assertEqual(
      (styles.StyleProperties.FontWeight, styles.FontWeightType.bold),
      self._declaration("font-weight: 700")
    )
    self.assertEqual(
      (styles.StyleProperties.FontWeight, styles.FontWeightType.normal),
      self._declaration("font-weight: 400")
    )

  def test_value_font_style(self):
    self.assertEqual(
      (styles.StyleProperties.FontStyle, styles.FontStyleType.italic),
      self._declaration("font-style: italic")
    )
    self.assertEqual(
      (styles.StyleProperties.FontStyle, styles.FontStyleType.oblique),
      self._declaration("font-style: oblique")
    )
    self.assertEqual(
      (styles.StyleProperties.FontStyle, styles.FontStyleType.normal),
      self._declaration("font-style: normal")
    )

  def test_value_text_decoration(self):
    self.assertEqual(
      (
        styles.StyleProperties.TextDecoration,
        styles.TextDecorationType(underline=True, line_through=False, overline=False)
      ),
      self._declaration("text-decoration: underline")
    )
    self.assertEqual(
      (
        styles.StyleProperties.TextDecoration,
        styles.TextDecorationType(underline=False, line_through=False, overline=False)
      ),
      self._declaration("text-decoration: none")
    )
    self.assertEqual(
      (
        styles.StyleProperties.TextDecoration,
        styles.TextDecorationType(underline=False, line_through=True, overline=False)
      ),
      self._declaration("text-decoration-line: line-through")
    )

  def test_value_line_height(self):
    self.assertEqual(
      (styles.StyleProperties.LineHeight, styles.SpecialValues.normal),
      self._declaration("line-height: normal")
    )
    self.assertEqual(
      (styles.StyleProperties.LineHeight, styles.LengthType(150, styles.LengthType.Units.pct)),
      self._declaration("line-height: 1.5")
    )
    self.assertEqual(
      (styles.StyleProperties.LineHeight, styles.LengthType(120, styles.LengthType.Units.pct)),
      self._declaration("line-height: 120%")
    )

  def test_value_opacity(self):
    self.assertEqual(
      (styles.StyleProperties.Opacity, 0.5),
      self._declaration("opacity: 0.5")
    )

  def test_value_visibility(self):
    self.assertEqual(
      (styles.StyleProperties.Visibility, styles.VisibilityType.hidden),
      self._declaration("visibility: hidden")
    )
    self.assertEqual(
      (styles.StyleProperties.Visibility, styles.VisibilityType.visible),
      self._declaration("visibility: visible")
    )

  def test_value_white_space(self):
    self.assertEqual(
      (styles.StyleProperties.WrapOption, styles.WrapOptionType.noWrap),
      self._declaration("white-space: nowrap")
    )
    self.assertEqual(
      (styles.StyleProperties.WrapOption, styles.WrapOptionType.noWrap),
      self._declaration("white-space: pre")
    )
    self.assertEqual(
      (styles.StyleProperties.WrapOption, styles.WrapOptionType.wrap),
      self._declaration("white-space: normal")
    )

  def test_value_direction(self):
    self.assertEqual(
      (styles.StyleProperties.Direction, styles.DirectionType.rtl),
      self._declaration("direction: rtl")
    )
    self.assertEqual(
      (styles.StyleProperties.Direction, styles.DirectionType.ltr),
      self._declaration("direction: ltr")
    )

  def test_value_unicode_bidi(self):
    self.assertEqual(
      (styles.StyleProperties.UnicodeBidi, styles.UnicodeBidiType.embed),
      self._declaration("unicode-bidi: embed")
    )
    self.assertEqual(
      (styles.StyleProperties.UnicodeBidi, styles.UnicodeBidiType.bidiOverride),
      self._declaration("unicode-bidi: bidi-override")
    )
    self.assertEqual(
      (styles.StyleProperties.UnicodeBidi, styles.UnicodeBidiType.normal),
      self._declaration("unicode-bidi: normal")
    )

  def test_value_ruby_position(self):
    self.assertEqual(
      (styles.StyleProperties.RubyPosition, styles.AnnotationPositionType.before),
      self._declaration("ruby-position: over")
    )
    self.assertEqual(
      (styles.StyleProperties.RubyPosition, styles.AnnotationPositionType.before),
      self._declaration("ruby-position: before")
    )
    self.assertEqual(
      (styles.StyleProperties.RubyPosition, styles.AnnotationPositionType.after),
      self._declaration("ruby-position: under")
    )
    self.assertEqual(
      (styles.StyleProperties.RubyPosition, styles.AnnotationPositionType.after),
      self._declaration("ruby-position: after")
    )
    self.assertEqual(
      (styles.StyleProperties.RubyPosition, styles.AnnotationPositionType.outside),
      self._declaration("ruby-position: outside")
    )

  def test_value_ruby_align(self):
    self.assertEqual(
      (styles.StyleProperties.RubyAlign, styles.RubyAlignType.center),
      self._declaration("ruby-align: center")
    )
    self.assertEqual(
      (styles.StyleProperties.RubyAlign, styles.RubyAlignType.spaceAround),
      self._declaration("ruby-align: space-around")
    )
    self.assertEqual(
      (styles.StyleProperties.RubyAlign, styles.RubyAlignType.spaceAround),
      self._declaration("ruby-align: space-between")
    )

  def test_value_text_combine_upright(self):
    self.assertEqual(
      (styles.StyleProperties.TextCombine, styles.TextCombineType.all),
      self._declaration("text-combine-upright: all")
    )
    self.assertEqual(
      (styles.StyleProperties.TextCombine, styles.TextCombineType.none),
      self._declaration("text-combine-upright: none")
    )

  def test_value_display(self):
    self.assertEqual(
      (styles.StyleProperties.Display, styles.DisplayType.none),
      self._declaration("display: none")
    )
    self.assertEqual(
      (styles.StyleProperties.Display, styles.DisplayType.auto),
      self._declaration("display: inline")
    )
    self.assertEqual(
      (styles.StyleProperties.Display, styles.DisplayType.auto),
      self._declaration("display: block")
    )

  def test_value_background_none(self):
    self.assertEqual(
      (styles.StyleProperties.BackgroundColor, styles.NamedColors.transparent.value),
      self._declaration("background: none")
    )

  def test_invalid_values_are_rejected(self):
    for declaration in (
        "color: not-a-color",
        "font-family: ,,,",
        "font-size: huge",
        "font-weight: heavy",
        "font-style: slanted",
        "text-decoration: blink",
        "line-height: tall",
        "opacity: half",
        "visibility: gone",
        "white-space: sideways",
        "direction: upwards",
        "unicode-bidi: reverse",
        "ruby-position: sideways",
        "ruby-align: left",
        "text-combine-upright: some",
        "display: table",
        "background: url(x.png) red",
    ):
      stylesheet = VttStyleSheet()
      stylesheet.add_css("::cue { " + declaration + " }")
      self.assertTrue(stylesheet.is_empty(), declaration)

  def test_declaration_without_colon(self):
    stylesheet = VttStyleSheet()
    stylesheet.add_css("::cue { color lime; color: red; }")

    self.assertEqual(
      {styles.StyleProperties.Color: styles.NamedColors.red.value},
      _values(stylesheet, CueElement(is_root=True))
    )

  def test_unterminated_comment(self):
    stylesheet = VttStyleSheet()
    stylesheet.add_css("::cue { color: red; } /* unterminated")

    self.assertEqual(
      {styles.StyleProperties.Color: styles.NamedColors.red.value},
      _values(stylesheet, CueElement(is_root=True))
    )

  def test_unterminated_at_rule(self):
    stylesheet = VttStyleSheet()
    stylesheet.add_css("@media screen { ::cue { color: red; }")

    self.assertTrue(stylesheet.is_empty())

  def test_unexpected_closing_brace(self):
    stylesheet = VttStyleSheet()
    stylesheet.add_css("} ::cue { color: lime; }")

    self.assertEqual(
      {styles.StyleProperties.Color: styles.NamedColors.lime.value},
      _values(stylesheet, CueElement(is_root=True))
    )

  def test_class_selector_with_multiple_classes(self):
    stylesheet = VttStyleSheet()
    stylesheet.add_css("::cue(.a.b) { color: lime; }")

    self.assertEqual(
      {styles.StyleProperties.Color: styles.NamedColors.lime.value},
      _values(stylesheet, CueElement(tag="c", classes=("a", "b")))
    )
    self.assertEqual({}, _values(stylesheet, CueElement(tag="c", classes=("a",))))

  def test_voice_selector_without_quotes(self):
    stylesheet = VttStyleSheet()
    stylesheet.add_css("::cue(v[voice=Mary]) { color: cyan; }")

    self.assertEqual(
      {styles.StyleProperties.Color: styles.NamedColors.cyan.value},
      _values(stylesheet, CueElement(tag="v", voice="Mary"))
    )

  def test_empty_selector_argument(self):
    stylesheet = VttStyleSheet()
    stylesheet.add_css("::cue() { color: red; }")

    self.assertTrue(stylesheet.is_empty())

  def test_selector_without_supported_tag(self):
    stylesheet = VttStyleSheet()
    stylesheet.add_css("::cue(span) { color: red; }")

    self.assertTrue(stylesheet.is_empty())

  def test_malformed_voice_selector(self):
    stylesheet = VttStyleSheet()
    stylesheet.add_css("::cue(v[lang=en]) { color: red; }")
    stylesheet.add_css('::cue(v[voice=""]) { color: red; }')
    stylesheet.add_css("::cue(v[voice=Mary) { color: red; }")

    self.assertTrue(stylesheet.is_empty())

  def test_selector_with_trailing_garbage(self):
    stylesheet = VttStyleSheet()
    stylesheet.add_css("::cue(b foo) { color: red; }")

    self.assertTrue(stylesheet.is_empty())

  def test_style_block_with_multiple_lines(self):
    stylesheet = VttStyleSheet()
    stylesheet.add_style_block([
      "::cue {",
      "  color: lime;",
      "}",
      "::cue(b) {",
      "  color: red;",
      "}",
    ])

    self.assertEqual(
      {styles.StyleProperties.Color: styles.NamedColors.lime.value},
      _values(stylesheet, CueElement(is_root=True))
    )
    self.assertEqual(
      {styles.StyleProperties.Color: styles.NamedColors.red.value},
      _values(stylesheet, CueElement(tag="b"))
    )

  def test_quoted_brace_in_value(self):
    stylesheet = VttStyleSheet()
    stylesheet.add_css('::cue { font-family: "a}b"; }')

    self.assertEqual(
      {styles.StyleProperties.FontFamily: ("a}b",)},
      _values(stylesheet, CueElement(is_root=True))
    )


if __name__ == '__main__':
  unittest.main()
