---
name: pdf2epub
description: A PDF becomes a real EPUB, set on paper white, with one violet signal.
colors:
  paper: "#faf7f0"
  panel: "#fffdf8"
  well: "#f4f0e7"
  line: "#e4ded2"
  line-strong: "#d3ccbe"
  ink: "#1b1916"
  ink-dim: "#5b564d"
  ink-faint: "#6f685b"
  accent: "#6b4ce6"
  accent-deep: "#553bc4"
  success: "#1f7a4d"
typography:
  display:
    fontFamily: "Newsreader, Georgia, serif"
    fontSize: "clamp(28px, 4.6vw, 42px)"
    fontWeight: 400
    lineHeight: 1.1
    letterSpacing: "-0.02em"
  heading:
    fontFamily: "Newsreader, Georgia, serif"
    fontSize: "19px"
    fontWeight: 600
    lineHeight: 1.25
    letterSpacing: "0"
  title:
    fontFamily: "Newsreader, Georgia, serif"
    fontSize: "14.5px"
    fontWeight: 600
    lineHeight: 1.3
  body:
    fontFamily: "ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.6
  body-small:
    fontFamily: "ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.55
  label:
    fontFamily: "JetBrains Mono, ui-monospace, SFMono-Regular, Menlo, monospace"
    fontSize: "11px"
    fontWeight: 400
    lineHeight: 1.4
    letterSpacing: "0.08em"
rounded:
  card: "6px"
  control: "6px"
  chip: "4px"
  pill: "99px"
spacing:
  xs: "8px"
  sm: "10px"
  md: "14px"
  lg: "18px"
  xl: "26px"
  section: "44px"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.panel}"
    typography: "{typography.body}"
    rounded: "{rounded.control}"
    padding: "13px 20px"
  button-primary-hover:
    backgroundColor: "{colors.accent-deep}"
    textColor: "{colors.panel}"
    rounded: "{rounded.control}"
  button-secondary:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.ink-dim}"
    typography: "{typography.body-small}"
    rounded: "{rounded.control}"
    padding: "10px 16px"
  input:
    backgroundColor: "{colors.well}"
    textColor: "{colors.ink}"
    typography: "{typography.body-small}"
    rounded: "{rounded.chip}"
    padding: "10px 11px"
  card:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.ink}"
    rounded: "{rounded.card}"
    padding: "20px"
  fact-chip:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink-dim}"
    typography: "{typography.label}"
    rounded: "{rounded.chip}"
    padding: "6px 10px"
  trust-pill:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink-dim}"
    typography: "{typography.label}"
    rounded: "{rounded.pill}"
    padding: "5px 11px"
---

# Design System: pdf2epub

## Overview

**Creative North Star: "The Colophon"**

The page should read like the last leaf of a well-made book: the one that states plainly what the book is, how it was made, and who made it. That is the whole argument for a serif display voice here. A converter is judged on whether the output looks like a book, so the page proving it is set like one. Paper white, black ink, hairline rules, and a single violet that behaves like a printed spot colour rather than a screen glow.

The surface is quiet by design. Nothing floats, nothing glows, nothing is the same size as anything it is not related to. Depth comes from two flat tones and a 1px rule, never from a shadow. Numbers stay in monospace because they are measurements of a real file, and the rest of the copy stays in a plain sans, because the reader came to convert something, not to read a brochure.

The shipped site is currently the dark incumbent. This file records the approved light direction, which replaces it. Do not carry dark-mode values back in without re-running the document pass.

**Key Characteristics:**
- Paper white ground, ink black text, one violet accent.
- Serif for headings and titles only. Sans for prose and controls. Mono for measured values only.
- Flat at rest. Hairlines and tone do all the separation work.
- The proof is the copy: the page shows real output numbers instead of describing quality.
- Roughly 100 words above the fold. If a line does not earn its place, it goes.

## Colors

Warm paper, cold ink, and one signal violet. The palette is deliberately low-contrast in its neutrals so the accent is the only saturated thing on the page.

### Primary
- **Signal Violet** (#6b4ce6): Every primary action, the one emphasised word in the display line, the small caps tags, and the mark's dot. It appears once per viewport cluster. On paper it has to be this dark: the lighter #8b6cff used in the dark incumbent measures about 3.4:1 on paper and fails for text.

### Neutral
- **Warm Paper** (#faf7f0): Page ground.
- **Sheet** (#fffdf8): Cards, which sit slightly above the ground rather than on it.
- **Well** (#f4f0e7): Inputs, drop zone, table of contents, and any recessed area.
- **Hairline** (#e4ded2): Every 1px rule and card border.
- **Hairline Strong** (#d3ccbe): Secondary button borders and hover borders.
- **Ink** (#1b1916): Display text and values.
- **Dulled Ink** (#5b564d): Body prose and lede.
- **Faint Ink** (#6f685b): Labels, table headers, footnotes.
- **Proof Green** (#1f7a4d): The word "free" in the trust pill, and nothing else.

### Named Rules
**The One Signal Rule.** Violet means "act here" or "this is the emphasised word". It never marks a section, a border, a background block, or a heading that is not also a link.

**The Paper Rule.** There is no grey. Every neutral is warmed toward the paper hue, so a screenshot of the page has no blue-grey in it.

## Typography

**Display Font:** Newsreader (self-hosted, with Georgia as the fallback)
**Body Font:** The system sans stack (no webfont, no download cost)
**Label/Mono Font:** JetBrains Mono (self-hosted, with ui-monospace fallback)

**Character:** A high-contrast reading serif against a neutral interface sans. The pairing says "this is a book, and the machine that made it is not showing off". The serif carries every heading; the sans carries every instruction.

### Hierarchy
- **Display** (400, clamp(28px, 4.6vw, 42px), 1.1, −0.02em): The hero line only. One per page.
- **Headline** (600, 19px, 1.25): Section headings such as "What it repairs".
- **Title** (600, 14.5px, 1.3): Card headings. Serif, same family as display, no letterspacing.
- **Body** (400, 16px, 1.6): Prose. Cap the measure at 54ch for the hero lede and 70ch elsewhere.
- **Body Small** (400, 13px, 1.55): Card subcopy, proof rows, footer.
- **Label** (400, 11px, 0.08em, uppercase): Table headers and the tags above tile titles. Monospace only.

### Named Rules
**The Two-Voice Rule.** Two families carry words: serif for headings, sans for everything you can click or read as an instruction. Mono is not a third voice, it is a measuring instrument, so it only ever holds numbers, keys, and the mono domain in the header.

**The No-Uppercase-Title Rule.** Uppercase belongs to labels only. Never set a heading or a card title in caps to make it feel technical.

## Layout

A single column, 940px maximum, 20px gutters, 72px of space below the last element. The hero puts the converter and the proof side by side in a 1.05fr / 0.95fr grid above 720px, and stacks them below it, converter first. Section rhythm is a 44px gap above a heading and 14px below it, so headings belong to the content under them rather than floating between blocks.

Vertical density is tight inside cards (14px between controls) and generous between sections. Nothing is centred except the drop zone's own text. The page never uses a horizontal rule between sections when a 44px gap will do; the only rules are the header underline, the proof rows, and the footer.

## Elevation & Depth

There are no shadows. Depth is two flat tones, a 1px hairline, and one recessed well tone. The card sits on the page by being marginally lighter than it; the input sits inside the card by being marginally darker. At no point does a blur appear.

### Named Rules
**The Flat Paper Rule.** If an element needs to look raised, change its tone by one step or give it a hairline. Never add a shadow, and never add a glow, including on the mark dot, which is a flat 8px circle.

## Shapes

Corners are close to square: 6px on cards and buttons, 4px on inputs and chips. That reads as a printed card rather than a web pill. The one exception is the trust pill in the header, a full 99px capsule, because it is a stamp on the page rather than a control. Borders are always 1px, never 2px, and the drop zone is the only dashed edge in the system.

## Components

### Buttons
- **Shape:** gently squared (6px), full width inside a card.
- **Primary:** violet ground, sheet-white label, 13px 20px padding, weight 700, 14.5px. One per card, and it is the only element on the page allowed to be fully saturated.
- **Hover:** accent drops to #553bc4. No lift, no shadow, no transform.
- **Secondary (sample):** transparent ground, 1px line-strong border, dulled ink label, 13px. Sits directly under the primary and must never compete with it.
- **Disabled:** 55% opacity, cursor wait.

### Inputs / Fields
- **Style:** recessed well ground, 1px hairline, 4px radius, 10px 11px padding, 13px sans.
- **Placeholder:** faint ink, always written as "Title (optional)" so the field's optionality is in the placeholder, not in a label above it.
- **Focus:** the border moves to the accent. No ring, no glow.
- **Layout:** title and author share a row; email gets its own row because it is the only field with a sales job.

### Cards
- **Corner Style:** 6px.
- **Background:** sheet, on paper ground.
- **Border:** 1px hairline.
- **Internal Padding:** 20px, 14px between controls.
- **Discipline:** a card heading is a title and nothing else. No subtitle under it. If the card needs explaining, the heading is wrong.

### Fact Chips
- **Style:** 1px hairline, 4px radius, 6px 10px padding, mono 12px, faint ink label with ink values inside.
- **Content:** only measured facts (200MB / 500 pages, OCR free, output formats). Never a benefit statement.

### Proof Table
- **Style:** full-bleed rows inside the card, no outer box, 1px hairline between rows, label left in faint ink, value right in mono ink.
- **Purpose:** this table is the page's argument. Rows are real counts from a real file, so they are never written by hand and never rounded.

### Drop Zone
- **Style:** dashed 1.5px line, 6px radius, well ground, 24px 16px padding, centred.
- **State:** border and ground shift only on drag-over. It is not a button, so it does not get the button's violet.

### Repairs Tiles
- **Style:** three tiles, 1px hairline, 4px radius, 12px padding, mono tag above a serif-free 12.5px bold title.
- **Discipline:** three tiles, not five. Each one names a repair the proof card cannot show.

### Header
- **Style:** mark on the left in serif 600 with a flat violet dot, mono domain in faint ink beside it, trust pill on the right.
- **Mobile:** the pill disappears below 560px. It is a reassurance, not navigation, so it may go before the mark does.

## Do's and Don'ts

### Do:
- **Do** keep the first screen near 100 words. The paid competitor in this market runs a heading, one sentence and a file input, and still sells credits.
- **Do** show the output as numbers and a real first paragraph. It is the one claim a competitor cannot copy without rebuilding their pipeline.
- **Do** set every heading in the serif and every control in the sans, at the exact sizes above.
- **Do** warm every neutral toward the paper hue, and keep the accent at #6b4ce6 on paper.
- **Do** let a card heading stand alone. Delete a subtitle before adding one.

### Don't:
- **Don't** explain what the proof card already shows in a sentence underneath it.
- **Don't** add a shadow, a glow, a gradient, or a second saturated colour.
- **Don't** use violet for a border, a background block, or a section marker.
- **Don't** put an uppercase mono tag on a heading. Tags belong to tiles and table headers only.
- **Don't** add a fourth typeface, or a serif fallback other than Georgia.
- **Don't** reintroduce the dark shell's #8b6cff on paper. It fails contrast and it weakens the single-signal rule.
