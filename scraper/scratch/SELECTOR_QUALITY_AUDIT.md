# Selector Quality Audit ? BitChute & Rumble

### [BitChute] `video_container` (manual)

**Selector under audit:**
```css
#video-card
```

**Matched element in dump** (paste the raw outer HTML of the matched node, trimmed):
```html
<div class="q-card q-card--flat no-shadow bg-transparent no-shadow no-border" dense="" id="video-card"><div class="q-card__section q-card__section--vert q-pa-none"><a class="q-item q-item-type row no-wrap q-item--clickable q-link cursor-pointer q-focusable q-hoverable q-py-none q-px-none" href="/video/KzK7T8QprVY" role="listitem" tabindex="0"><div class="q-focus-helper" tabindex="-1"></div><div aria-label="Video" class="q-img q-img--menu bc-border-radius" role="img"><div style="padding-bottom: 56.25%;"></div><div class="q-img__container absolute-full"><img alt="Video" aria-hidden="true" class="q-img__image q-img__image--with-transition q-img__image--loaded" draggable="false" fetchpriority="auto" loading="lazy" src="https://static-3.bitchute.com/live/cover_images/rfcShUDnIez0/KzK7T8QprVY_640x360.jpg" style="object-fit: cover; object-position: 50% 50%;"/></div><div class="q-img__content ab
```

**Match count**: `6` (expected: 6 (BitChute cards))

| Dimension | Verdict | Finding |
|---|---|---|
| Stability | `ACCEPTABLE` | Selector uses a reasonably stable structural anchor. |
| Precision | `PRECISE` | List selector matches 6 nodes in this dump. |
| Accuracy | `ACCURATE` | Matched node contains target value directly. |
| Robustness | `ROBUST` | Selector works on current template and degrades to empty list if field absent. |
| Reliability | `RELIABLE` | Value is present in rendered dump without interaction. |

**Overall grade**: `PASS`


---

### [BitChute] `video_title` (manual)

**Selector under audit:**
```css
.q-item__label.bc-text-break.ellipsis-2-lines.bc-responsive-font
```

**Matched element in dump** (paste the raw outer HTML of the matched node, trimmed):
```html
<div class="q-item__label bc-text-break ellipsis-2-lines bc-responsive-font">What Ozempic is Doing to Your Liver <!-- --></div>
```

**Match count**: `6` (expected: 6 (BitChute cards))

| Dimension | Verdict | Finding |
|---|---|---|
| Stability | `FRAGILE` | Selector depends on styling classes. |
| Precision | `PRECISE` | List selector matches 6 nodes in this dump. |
| Accuracy | `ACCURATE` | Matched node contains target value directly. |
| Robustness | `ROBUST` | Selector works on current template and degrades to empty list if field absent. |
| Reliability | `RELIABLE` | Value is present in rendered dump without interaction. |

**Overall grade**: `PASS-WITH-NOTES`


---

### [BitChute] `video_views` (manual)

**Selector under audit:**
```css
.absolute-bottom-left .text-caption
```

**Matched element in dump** (paste the raw outer HTML of the matched node, trimmed):
```html
<div class="text-caption">1,561</div>
```

**Match count**: `6` (expected: 6 (BitChute cards))

| Dimension | Verdict | Finding |
|---|---|---|
| Stability | `ACCEPTABLE` | Selector uses a reasonably stable structural anchor. |
| Precision | `PRECISE` | List selector matches 6 nodes in this dump. |
| Accuracy | `NEEDS-CLEANING` | Numeric text includes words/symbols and must be normalized. |
| Robustness | `ROBUST` | Selector works on current template and degrades to empty list if field absent. |
| Reliability | `RELIABLE` | Value is present in rendered dump without interaction. |

**Overall grade**: `PASS`


---

### [BitChute] `video_duration` (manual)

**Selector under audit:**
```css
.absolute-bottom-right .text-caption
```

**Matched element in dump** (paste the raw outer HTML of the matched node, trimmed):
```html
<div class="text-caption">10:33</div>
```

**Match count**: `6` (expected: 6 (BitChute cards))

| Dimension | Verdict | Finding |
|---|---|---|
| Stability | `ACCEPTABLE` | Selector uses a reasonably stable structural anchor. |
| Precision | `PRECISE` | List selector matches 6 nodes in this dump. |
| Accuracy | `ACCURATE` | Matched node contains target value directly. |
| Robustness | `ROBUST` | Selector works on current template and degrades to empty list if field absent. |
| Reliability | `RELIABLE` | Value is present in rendered dump without interaction. |

**Overall grade**: `PASS`


---

### [BitChute] `video_upload_dates` (manual)

**Selector under audit:**
```css
.q-item__label.q-item__label--caption.text-caption
```

**Matched element in dump** (paste the raw outer HTML of the matched node, trimmed):
```html
<div class="q-item__label q-item__label--caption text-caption bc-text-break ellipsis"></div>
```

**Match count**: `18` (expected: 6 (BitChute cards))

| Dimension | Verdict | Finding |
|---|---|---|
| Stability | `FRAGILE` | Selector depends on styling classes. |
| Precision | `PRECISE` | List selector matches 18 nodes in this dump. |
| Accuracy | `NEEDS-CLEANING` | Relative display text requires parsing; machine-readable datetime is preferred when available. |
| Robustness | `ROBUST` | Selector works on current template and degrades to empty list if field absent. |
| Reliability | `RACE-RISK` | BitChute uses Vue hydration markers; early capture can return incomplete values. |

**Overall grade**: `REPLACE`

**Recommended replacement** *(only for REPLACE or CRITICAL grades)*:
```css
#video-card .q-item__label.q-item__label--caption.text-caption
```

**Why it is better**: The replacement narrows scope to the correct semantic region and reduces over-selection risk while preserving extraction reliability in rendered DOM.

**Extraction note**: `text()` unless attribute-specific (`attr(href)`, `attr(datetime)`, `attr(data-views)`).

**Normalization note**: Strip whitespace; parse abbreviated counts (`K/M/B`) and remove label suffixes.

---

### [BitChute] `subscriber_count` (manual)

**Selector under audit:**
```css
span[style*="cursor: pointer;"]
```

**Matched element in dump** (paste the raw outer HTML of the matched node, trimmed):
```html
<span data-v-1952597e="" style="cursor: pointer;">204 subscribers <!-- --></span>
```

**Match count**: `1` (expected: 1)

| Dimension | Verdict | Finding |
|---|---|---|
| Stability | `ACCEPTABLE` | Selector uses a reasonably stable structural anchor. |
| Precision | `PRECISE` | Singleton selector resolves to exactly one node. |
| Accuracy | `NEEDS-CLEANING` | Numeric text includes words/symbols and must be normalized. |
| Robustness | `ROBUST` | Selector works on current template and degrades to empty list if field absent. |
| Reliability | `RACE-RISK` | BitChute uses Vue hydration markers; early capture can return incomplete values. |

**Overall grade**: `REPLACE`

**Recommended replacement** *(only for REPLACE or CRITICAL grades)*:
```css
meta[property="og:title"]
```

**Why it is better**: The replacement narrows scope to the correct semantic region and reduces over-selection risk while preserving extraction reliability in rendered DOM.

**Extraction note**: `text()` unless attribute-specific (`attr(href)`, `attr(datetime)`, `attr(data-views)`).

**Normalization note**: Strip whitespace; parse abbreviated counts (`K/M/B`) and remove label suffixes.

---

### [BitChute] `total_videos` (manual)

**Selector under audit:**
```css
span
```

**Matched element in dump** (paste the raw outer HTML of the matched node, trimmed):
```html
<span class="q-focus-helper" tabindex="-1"></span>
```

**Match count**: `40` (expected: 1)

| Dimension | Verdict | Finding |
|---|---|---|
| Stability | `ACCEPTABLE` | Selector uses a reasonably stable structural anchor. |
| Precision | `OVER-SELECTS` | Singleton selector matches 40 nodes and is ambiguous. |
| Accuracy | `ACCURATE` | Matched node contains target value directly. |
| Robustness | `TEMPLATE-DEPENDENT` | Broad selector is sensitive to layout/template variation. |
| Reliability | `RELIABLE` | Value is present in rendered dump without interaction. |

**Overall grade**: `REPLACE`

**Recommended replacement** *(only for REPLACE or CRITICAL grades)*:
```css
span:-soup-contains('videos')
```

**Why it is better**: The replacement narrows scope to the correct semantic region and reduces over-selection risk while preserving extraction reliability in rendered DOM.

**Extraction note**: `text()` unless attribute-specific (`attr(href)`, `attr(datetime)`, `attr(data-views)`).

**Normalization note**: Strip whitespace; parse abbreviated counts (`K/M/B`) and remove label suffixes.

---

### [BitChute] `about_description` (manual)

**Selector under audit:**
```css
div[style*="white-space: pre-line;"]
```

**Matched element in dump** (paste the raw outer HTML of the matched node, trimmed):
```html
<div data-v-1952597e="" style="white-space: pre-line;">With over 43,000,000 followers worldwide, Dr. Eric Berg DC spreads the truth about getting healthy and losing weight. Dr. Berg, age 60, specializes in Healthy Keto® and Intermittent Fasting. He is the director of Dr. Berg's Nutritionals and a best-selling Amazon author.

His book, The Healthy Keto Plan describes specific strategies on doing the healthy version of the ketogenic diet as well as intermittent
fasting. He has conducted over 4800 seminars on health-related topics and trained over 2500 doctors world-wide in his methods. Dr. Berg breaks down confusing complex health topics into easy to understand, usable knowledge. 

For more information, go to our website at <a class="text-red-5" href="http://www.drberg.com" target="_blank">www.drberg.com</a> or call customer service at 703-354-7336. Much of the details of Dr. Berg's progra
```

**Match count**: `1` (expected: 1)

| Dimension | Verdict | Finding |
|---|---|---|
| Stability | `ACCEPTABLE` | Selector uses a reasonably stable structural anchor. |
| Precision | `PRECISE` | Singleton selector resolves to exactly one node. |
| Accuracy | `ACCURATE` | Matched node contains target value directly. |
| Robustness | `ROBUST` | Selector works on current template and degrades to empty list if field absent. |
| Reliability | `RELIABLE` | Value is present in rendered dump without interaction. |

**Overall grade**: `PASS`


---

### [BitChute] `about_details` (manual)

**Selector under audit:**
```css
.q-item__label.text-bold
```

**Matched element in dump** (paste the raw outer HTML of the matched node, trimmed):
```html
<div class="q-item__label text-bold" data-v-1952597e="">204</div>
```

**Match count**: `5` (expected: N list items)

| Dimension | Verdict | Finding |
|---|---|---|
| Stability | `FRAGILE` | Selector depends on styling classes. |
| Precision | `PRECISE` | List selector matches 5 nodes in this dump. |
| Accuracy | `ACCURATE` | Matched node contains target value directly. |
| Robustness | `ROBUST` | Selector works on current template and degrades to empty list if field absent. |
| Reliability | `RELIABLE` | Value is present in rendered dump without interaction. |

**Overall grade**: `PASS-WITH-NOTES`


---

### [BitChute] `video_comment_count` (manual)

**Selector under audit:**
```css
span.item.count .value
```

**Matched element in dump** (paste the raw outer HTML of the matched node, trimmed):
```html
<span class="value">19</span>
```

**Match count**: `2` (expected: 1)

| Dimension | Verdict | Finding |
|---|---|---|
| Stability | `ACCEPTABLE` | Selector uses a reasonably stable structural anchor. |
| Precision | `OVER-SELECTS` | Singleton selector matches 2 nodes and is ambiguous. |
| Accuracy | `NEEDS-CLEANING` | Numeric text includes words/symbols and must be normalized. |
| Robustness | `TEMPLATE-DEPENDENT` | Broad selector is sensitive to layout/template variation. |
| Reliability | `RELIABLE` | Value is present in rendered dump without interaction. |

**Overall grade**: `REPLACE`

**Recommended replacement** *(only for REPLACE or CRITICAL grades)*:
```css
span.item.count .value:first-of-type
```

**Why it is better**: The replacement narrows scope to the correct semantic region and reduces over-selection risk while preserving extraction reliability in rendered DOM.

**Extraction note**: `text()` unless attribute-specific (`attr(href)`, `attr(datetime)`, `attr(data-views)`).

**Normalization note**: Strip whitespace; parse abbreviated counts (`K/M/B`) and remove label suffixes.

---

### [Rumble] `video_views` (manual)

**Selector under audit:**
```css
span.videostream__data--subitem.videostream__views--count
```

**Matched element in dump** (paste the raw outer HTML of the matched node, trimmed):
```html
<span class="videostream__data--subitem videostream__views--count"> 26 </span>
```

**Match count**: `28` (expected: 28 (Rumble cards))

| Dimension | Verdict | Finding |
|---|---|---|
| Stability | `FRAGILE` | Selector depends on styling classes. |
| Precision | `PRECISE` | List selector matches 28 nodes in this dump. |
| Accuracy | `NEEDS-CLEANING` | Numeric text includes words/symbols and must be normalized. |
| Robustness | `ROBUST` | Selector works on current template and degrades to empty list if field absent. |
| Reliability | `RELIABLE` | Value is present in rendered dump without interaction. |

**Overall grade**: `PASS-WITH-NOTES`


---

### [Rumble] `video_upload_dates` (manual)

**Selector under audit:**
```css
time.videostream__data--subitem.videostream__time
```

**Matched element in dump** (paste the raw outer HTML of the matched node, trimmed):
```html
<time class="videostream__data--subitem videostream__time" datetime="2026-05-25T00:04:35-04:00">
						3 hours ago					</time>
```

**Match count**: `28` (expected: 28 (Rumble cards))

| Dimension | Verdict | Finding |
|---|---|---|
| Stability | `FRAGILE` | Selector depends on styling classes. |
| Precision | `PRECISE` | List selector matches 28 nodes in this dump. |
| Accuracy | `NEEDS-CLEANING` | Relative display text requires parsing; machine-readable datetime is preferred when available. |
| Robustness | `ROBUST` | Selector works on current template and degrades to empty list if field absent. |
| Reliability | `RELIABLE` | Value is present in rendered dump without interaction. |

**Overall grade**: `PASS-WITH-NOTES`


---

### [Rumble] `video_title` (manual)

**Selector under audit:**
```css
h3.thumbnail__title.line-clamp-2
```

**Matched element in dump** (paste the raw outer HTML of the matched node, trimmed):
```html
<h3 class="thumbnail__title line-clamp-2" title="THEY SOLD THEIR BITCOIN… AND IT WILL HAUNT THEM FOREVER">
					THEY SOLD THEIR BITCOIN… AND IT WILL HAUNT THEM FOREVER				</h3>
```

**Match count**: `28` (expected: 28 (Rumble cards))

| Dimension | Verdict | Finding |
|---|---|---|
| Stability | `FRAGILE` | Selector depends on styling classes. |
| Precision | `PRECISE` | List selector matches 28 nodes in this dump. |
| Accuracy | `ACCURATE` | Matched node contains target value directly. |
| Robustness | `ROBUST` | Selector works on current template and degrades to empty list if field absent. |
| Reliability | `RELIABLE` | Value is present in rendered dump without interaction. |

**Overall grade**: `PASS-WITH-NOTES`


---

### [Rumble] `about_description` (manual)

**Selector under audit:**
```css
div.channel-about--description
```

**Matched element in dump** (paste the raw outer HTML of the matched node, trimmed):
```html
<div class="channel-about--description">
<h1 class="channel-about--title">Description</h1>
<p>Talking About Bitcoin, Blockchain and life</p>
</div>
```

**Match count**: `1` (expected: 1)

| Dimension | Verdict | Finding |
|---|---|---|
| Stability | `FRAGILE` | Selector depends on styling classes. |
| Precision | `PRECISE` | Singleton selector resolves to exactly one node. |
| Accuracy | `ACCURATE` | Matched node contains target value directly. |
| Robustness | `ROBUST` | Selector works on current template and degrades to empty list if field absent. |
| Reliability | `RELIABLE` | Value is present in rendered dump without interaction. |

**Overall grade**: `PASS-WITH-NOTES`


---

### [Rumble] `social_links` (manual)

**Selector under audit:**
```css
div.channel-about--socials a.channel-about--socials-item
```

**Matched element in dump** (paste the raw outer HTML of the matched node, trimmed):
```html
<a class="channel-about--socials-item" href="https://twitter.com/thebitcoinfam" rel="nofollow noopener" target="_blank">
<svg class="socials-icon theme-black-white" fill="none" height="22" viewbox="0 0 24 24" width="22"><g clip-path="url(#clip0_5044_185873)">
<path d="M13.7124 10.5411L20.4133 2.5H18.8255L13.0071 9.48195L8.35992 2.5H3L10.0274 13.0579L3 21.4902H4.58799L10.7324 14.1171L15.6401 21.4902H21L13.7121 10.5411H13.7124ZM11.5375 13.151L10.8255 12.0996L5.16016 3.73406H7.59922L12.1712 10.4853L12.8832 11.5367L18.8262 20.3123H16.3871L11.5375 13.1514V13.151Z" fill="currentColor"></path>
</g>
<defs>
<clippath id="clip0_5044_185873">
<rect fill="white" height="19" transform="translate(3 2.5)" width="18"></rect>
</clippath>
</defs></svg>Twitter								</a>
```

**Match count**: `3` (expected: N list items)

| Dimension | Verdict | Finding |
|---|---|---|
| Stability | `FRAGILE` | Selector depends on styling classes. |
| Precision | `PRECISE` | List selector matches 3 nodes in this dump. |
| Accuracy | `ACCURATE` | Matched node contains target value directly. |
| Robustness | `ROBUST` | Selector works on current template and degrades to empty list if field absent. |
| Reliability | `RELIABLE` | Value is present in rendered dump without interaction. |

**Overall grade**: `PASS-WITH-NOTES`


---

### [Rumble] `about_additional_details` (manual)

**Selector under audit:**
```css
div.channel-about-sidebar--inner
```

**Matched element in dump** (paste the raw outer HTML of the matched node, trimmed):
```html
<div class="channel-about-sidebar--inner">
<h2 class="channel-about--title">Additional Details</h2>
<p><svg class="sidebar-details-icon" height="16" viewbox="0 0 16 16" width="16"><path clip-rule="evenodd" d="M11.4165 1.33337C11.4165 0.91916 11.0807 0.583374 10.6665 0.583374C10.2523 0.583374 9.9165 0.91916 9.9165 1.33337V1.91663H6.0835V1.33337C6.0835 0.91916 5.74771 0.583374 5.3335 0.583374C4.91928 0.583374 4.5835 0.91916 4.5835 1.33337V1.91663H3.33333C2.18274 1.91663 1.25 2.84937 1.25 3.99996V13.3333C1.25 14.4839 2.18274 15.4166 3.33333 15.4166H12.6667C13.8173 15.4166 14.75 14.4839 14.75 13.3333V3.99996C14.75 2.84937 13.8173 1.91663 12.6667 1.91663H11.4165V1.33337ZM13.25 5.91663V3.99996C13.25 3.67779 12.9888 3.41663 12.6667 3.41663H11.4165V4.00004C11.4165 4.41425 11.0807 4.75004 10.6665 4.75004C10.2523 4.75004 9.9165 4.41425 9.9165 4.00004V3.41663H6.0835V4.00004C6.0835 4.41425 5.74771 4
```

**Match count**: `1` (expected: 1)

| Dimension | Verdict | Finding |
|---|---|---|
| Stability | `ACCEPTABLE` | Selector uses a reasonably stable structural anchor. |
| Precision | `PRECISE` | Singleton selector resolves to exactly one node. |
| Accuracy | `ACCURATE` | Matched node contains target value directly. |
| Robustness | `ROBUST` | Selector works on current template and degrades to empty list if field absent. |
| Reliability | `RELIABLE` | Value is present in rendered dump without interaction. |

**Overall grade**: `PASS`


---

### [Rumble] `video_comment_count` (manual)

**Selector under audit:**
```css
h3.comment-count
```

**Matched element in dump** (paste the raw outer HTML of the matched node, trimmed):
```html
<h3 class="comment-count">23 Comments </h3>
```

**Match count**: `1` (expected: 1)

| Dimension | Verdict | Finding |
|---|---|---|
| Stability | `ACCEPTABLE` | Selector uses a reasonably stable structural anchor. |
| Precision | `PRECISE` | Singleton selector resolves to exactly one node. |
| Accuracy | `NEEDS-CLEANING` | Numeric text includes words/symbols and must be normalized. |
| Robustness | `ROBUST` | Selector works on current template and degrades to empty list if field absent. |
| Reliability | `RELIABLE` | Value is present in rendered dump without interaction. |

**Overall grade**: `PASS`


---

### [Rumble] `video_container` (code)

**Selector under audit:**
```css
div.videostream.thumbnail__grid--item
```

**Matched element in dump** (paste the raw outer HTML of the matched node, trimmed):
```html
<div class="videostream thumbnail__grid--item" data-video-id="436970680" role="listitem">
<div class="thumbnail__thumb">
<img alt="THEY SOLD THEIR BITCOIN… AND IT WILL HAUNT THEM FOREVER" class="thumbnail__image" draggable="false" height="270" loading="lazy" onerror="this.onerror=null;this.src=&quot;data:image/svg+xml,%3Csvg width='480' height='270' xmlns='http://www.w3.org/2000/svg'/%3E&quot;" src="https://hugh.cdn.rumble.cloud/video/fwe2/a7/s8/1/a/x/6/q/ax6qA.oq1b-small-THEY-SOLD-THEIR-BITCOIN-AND..jpg" width="480"/>
<div class="videostream__info videostream__info--bottom">
<div class="videostream__badge videostream__status videostream__status--duration">
				16:20			</div>
</div>
<a class="videostream__link link" draggable="false" href="/v7acgqo-they-sold-their-bitcoin-and-it-will-haunt-them-forever.html?e9s=src_v1_cmd%2Csrc_v1_ucp_a"></a>
</div>
<div class="videostream__footer">
<a c
```

**Match count**: `28` (expected: 28 (Rumble cards))

| Dimension | Verdict | Finding |
|---|---|---|
| Stability | `FRAGILE` | Selector depends on styling classes. |
| Precision | `PRECISE` | List selector matches 28 nodes in this dump. |
| Accuracy | `ACCURATE` | Matched node contains target value directly. |
| Robustness | `ROBUST` | Selector works on current template and degrades to empty list if field absent. |
| Reliability | `RELIABLE` | Value is present in rendered dump without interaction. |

**Overall grade**: `PASS-WITH-NOTES`


---

### [Rumble] `video_url` (code)

**Selector under audit:**
```css
a.videostream__link[href*="/v"]
```

**Matched element in dump** (paste the raw outer HTML of the matched node, trimmed):
```html
<a class="videostream__link link" draggable="false" href="/v7acgqo-they-sold-their-bitcoin-and-it-will-haunt-them-forever.html?e9s=src_v1_cmd%2Csrc_v1_ucp_a"></a>
```

**Match count**: `28` (expected: 28 (Rumble cards))

| Dimension | Verdict | Finding |
|---|---|---|
| Stability | `FRAGILE` | Selector depends on styling classes. |
| Precision | `PRECISE` | List selector matches 28 nodes in this dump. |
| Accuracy | `ACCURATE` | Matched node contains target value directly. |
| Robustness | `ROBUST` | Selector works on current template and degrades to empty list if field absent. |
| Reliability | `RELIABLE` | Value is present in rendered dump without interaction. |

**Overall grade**: `PASS-WITH-NOTES`


---

### [Rumble] `video_title` (code)

**Selector under audit:**
```css
h3.thumbnail__title
```

**Matched element in dump** (paste the raw outer HTML of the matched node, trimmed):
```html
<h3 class="thumbnail__title line-clamp-2" title="THEY SOLD THEIR BITCOIN… AND IT WILL HAUNT THEM FOREVER">
					THEY SOLD THEIR BITCOIN… AND IT WILL HAUNT THEM FOREVER				</h3>
```

**Match count**: `28` (expected: 28 (Rumble cards))

| Dimension | Verdict | Finding |
|---|---|---|
| Stability | `FRAGILE` | Selector depends on styling classes. |
| Precision | `PRECISE` | List selector matches 28 nodes in this dump. |
| Accuracy | `ACCURATE` | Matched node contains target value directly. |
| Robustness | `ROBUST` | Selector works on current template and degrades to empty list if field absent. |
| Reliability | `RELIABLE` | Value is present in rendered dump without interaction. |

**Overall grade**: `PASS-WITH-NOTES`


---

### [Rumble] `video_time` (code)

**Selector under audit:**
```css
time.videostream__time
```

**Matched element in dump** (paste the raw outer HTML of the matched node, trimmed):
```html
<time class="videostream__data--subitem videostream__time" datetime="2026-05-25T00:04:35-04:00">
						3 hours ago					</time>
```

**Match count**: `28` (expected: 28 (Rumble cards))

| Dimension | Verdict | Finding |
|---|---|---|
| Stability | `FRAGILE` | Selector depends on styling classes. |
| Precision | `PRECISE` | List selector matches 28 nodes in this dump. |
| Accuracy | `NEEDS-CLEANING` | Relative display text requires parsing; machine-readable datetime is preferred when available. |
| Robustness | `ROBUST` | Selector works on current template and degrades to empty list if field absent. |
| Reliability | `RELIABLE` | Value is present in rendered dump without interaction. |

**Overall grade**: `PASS-WITH-NOTES`


---

### [Rumble] `video_views` (code)

**Selector under audit:**
```css
span.videostream__views[data-views]
```

**Matched element in dump** (paste the raw outer HTML of the matched node, trimmed):
```html
<span class="videostream__data--item videostream__views" data-views="26" title="26">
<svg class="videostream__data--subitem videostream__data--icon" height="11" viewbox="0 0 15 11" width="15"><path d="M1.4 5.7s2.3-4.5 6.3-4.5S14 5.7 14 5.7s-2.3 4.6-6.3 4.6-6.3-4.6-6.3-4.6Z" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.4"></path><path d="M7.7 7.6a1.8 1.8 0 1 0 0-3.7 1.8 1.8 0 0 0 0 3.7Z" fill="currentColor"></path></svg> <span class="videostream__data--subitem videostream__views--count"> 26 </span>
<span class="videostream__data--subitem videostream__views--text">
						views					</span>
</span>
```

**Match count**: `28` (expected: 28 (Rumble cards))

| Dimension | Verdict | Finding |
|---|---|---|
| Stability | `STABLE` | Selector uses a reasonably stable structural anchor. |
| Precision | `PRECISE` | List selector matches 28 nodes in this dump. |
| Accuracy | `NEEDS-CLEANING` | Numeric text includes words/symbols and must be normalized. |
| Robustness | `ROBUST` | Selector works on current template and degrades to empty list if field absent. |
| Reliability | `RELIABLE` | Value is present in rendered dump without interaction. |

**Overall grade**: `PASS`


---

### [Rumble] `video_view_count_text` (code)

**Selector under audit:**
```css
span.videostream__views--count
```

**Matched element in dump** (paste the raw outer HTML of the matched node, trimmed):
```html
<span class="videostream__data--subitem videostream__views--count"> 26 </span>
```

**Match count**: `28` (expected: 28 (Rumble cards))

| Dimension | Verdict | Finding |
|---|---|---|
| Stability | `FRAGILE` | Selector depends on styling classes. |
| Precision | `PRECISE` | List selector matches 28 nodes in this dump. |
| Accuracy | `ACCURATE` | Matched node contains target value directly. |
| Robustness | `ROBUST` | Selector works on current template and degrades to empty list if field absent. |
| Reliability | `RELIABLE` | Value is present in rendered dump without interaction. |

**Overall grade**: `PASS-WITH-NOTES`


---

### [Rumble] `video_comments` (code)

**Selector under audit:**
```css
span.videostream__comments
```

**Matched element in dump** (paste the raw outer HTML of the matched node, trimmed):
```html
<span class="videostream__data--item videostream__comments" title="1">
<svg class="videostream__data--subitem videostream__data--icon" fill="none" height="16" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" viewbox="0 0 16 16" width="16"> <path d="M14 10C14 10.3536 13.8595 10.6928 13.6095 10.9428C13.3594 11.1929 13.0203 11.3333 12.6667 11.3333H4.66667L2 14V3.33333C2 2.97971 2.14048 2.64057 2.39052 2.39052C2.64057 2.14048 2.97971 2 3.33333 2H12.6667C13.0203 2 13.3594 2.14048 13.6095 2.39052C13.8595 2.64057 14 2.97971 14 3.33333V10Z"></path></svg> <span class="videostream__data--subitem videostream__comments--count">
						1					</span>
<span class="videostream__data--subitem videostream__data--description">
						comment					</span>
</span>
```

**Match count**: `21` (expected: 28 (Rumble cards))

| Dimension | Verdict | Finding |
|---|---|---|
| Stability | `FRAGILE` | Selector depends on styling classes. |
| Precision | `PRECISE` | List selector matches 21 nodes in this dump. |
| Accuracy | `ACCURATE` | Matched node contains target value directly. |
| Robustness | `ROBUST` | Selector works on current template and degrades to empty list if field absent. |
| Reliability | `RELIABLE` | Value is present in rendered dump without interaction. |

**Overall grade**: `PASS-WITH-NOTES`


---

### [Rumble] `video_comment_count_text` (code)

**Selector under audit:**
```css
span.videostream__comments--count
```

**Matched element in dump** (paste the raw outer HTML of the matched node, trimmed):
```html
<span class="videostream__data--subitem videostream__comments--count">
						1					</span>
```

**Match count**: `21` (expected: 28 (Rumble cards))

| Dimension | Verdict | Finding |
|---|---|---|
| Stability | `FRAGILE` | Selector depends on styling classes. |
| Precision | `PRECISE` | List selector matches 21 nodes in this dump. |
| Accuracy | `ACCURATE` | Matched node contains target value directly. |
| Robustness | `ROBUST` | Selector works on current template and degrades to empty list if field absent. |
| Reliability | `RELIABLE` | Value is present in rendered dump without interaction. |

**Overall grade**: `PASS-WITH-NOTES`


---

### [Rumble] `channel_name` (code)

**Selector under audit:**
```css
.channel-header--title h1
```

**Matched element in dump** (paste the raw outer HTML of the matched node, trimmed):
```html
<h1>The Bitcoin Family</h1>
```

**Match count**: `1` (expected: 1)

| Dimension | Verdict | Finding |
|---|---|---|
| Stability | `FRAGILE` | Selector depends on styling classes. |
| Precision | `PRECISE` | Singleton selector resolves to exactly one node. |
| Accuracy | `ACCURATE` | Matched node contains target value directly. |
| Robustness | `ROBUST` | Selector works on current template and degrades to empty list if field absent. |
| Reliability | `RELIABLE` | Value is present in rendered dump without interaction. |

**Overall grade**: `PASS-WITH-NOTES`


---

### [Rumble] `subscriber_count` (code)

**Selector under audit:**
```css
.channel-header--title span span
```

**Matched element in dump** (paste the raw outer HTML of the matched node, trimmed):
```html
<span>2.98K Followers</span>
```

**Match count**: `1` (expected: 1)

| Dimension | Verdict | Finding |
|---|---|---|
| Stability | `FRAGILE` | Selector depends on styling classes. |
| Precision | `PRECISE` | Singleton selector resolves to exactly one node. |
| Accuracy | `NEEDS-CLEANING` | Numeric text includes words/symbols and must be normalized. |
| Robustness | `ROBUST` | Selector works on current template and degrades to empty list if field absent. |
| Reliability | `RELIABLE` | Value is present in rendered dump without interaction. |

**Overall grade**: `PASS-WITH-NOTES`


---

### [Rumble] `channel_description` (code)

**Selector under audit:**
```css
.channel-about--description > p
```

**Matched element in dump** (paste the raw outer HTML of the matched node, trimmed):
```html
<p>Talking About Bitcoin, Blockchain and life</p>
```

**Match count**: `1` (expected: 1)

| Dimension | Verdict | Finding |
|---|---|---|
| Stability | `ACCEPTABLE` | Selector uses a reasonably stable structural anchor. |
| Precision | `PRECISE` | Singleton selector resolves to exactly one node. |
| Accuracy | `ACCURATE` | Matched node contains target value directly. |
| Robustness | `ROBUST` | Selector works on current template and degrades to empty list if field absent. |
| Reliability | `RELIABLE` | Value is present in rendered dump without interaction. |

**Overall grade**: `PASS`


---

### [Rumble] `external_links` (code)

**Selector under audit:**
```css
.channel-about--socials a.channel-about--socials-item[href]
```

**Matched element in dump** (paste the raw outer HTML of the matched node, trimmed):
```html
<a class="channel-about--socials-item" href="https://twitter.com/thebitcoinfam" rel="nofollow noopener" target="_blank">
<svg class="socials-icon theme-black-white" fill="none" height="22" viewbox="0 0 24 24" width="22"><g clip-path="url(#clip0_5044_185873)">
<path d="M13.7124 10.5411L20.4133 2.5H18.8255L13.0071 9.48195L8.35992 2.5H3L10.0274 13.0579L3 21.4902H4.58799L10.7324 14.1171L15.6401 21.4902H21L13.7121 10.5411H13.7124ZM11.5375 13.151L10.8255 12.0996L5.16016 3.73406H7.59922L12.1712 10.4853L12.8832 11.5367L18.8262 20.3123H16.3871L11.5375 13.1514V13.151Z" fill="currentColor"></path>
</g>
<defs>
<clippath id="clip0_5044_185873">
<rect fill="white" height="19" transform="translate(3 2.5)" width="18"></rect>
</clippath>
</defs></svg>Twitter								</a>
```

**Match count**: `3` (expected: N list items)

| Dimension | Verdict | Finding |
|---|---|---|
| Stability | `FRAGILE` | Selector depends on styling classes. |
| Precision | `PRECISE` | List selector matches 3 nodes in this dump. |
| Accuracy | `ACCURATE` | Matched node contains target value directly. |
| Robustness | `ROBUST` | Selector works on current template and degrades to empty list if field absent. |
| Reliability | `RELIABLE` | Value is present in rendered dump without interaction. |

**Overall grade**: `PASS-WITH-NOTES`


---

### [Rumble] `view_count_video` (code)

**Selector under audit:**
```css
.media-description-info-views
```

**Matched element in dump** (paste the raw outer HTML of the matched node, trimmed):
```html
<div class="media-description-info-views">
<svg height="14" viewbox="1 2 12 12" width="14"> <path d="M4.48 13.1c-.85.39-1.81-.18-1.92-1.13a37.58 37.58 0 0 1 0-8.3 1.36 1.36 0 0 1 1.92-1.13 31.45 31.45 0 0 1 3.39 1.84 32.28 32.28 0 0 1 3.27 2.33c.7.57.7 1.65 0 2.22a32.27 32.27 0 0 1-3.27 2.33 31.5 31.5 0 0 1-3.4 1.84Z" fill="currentColor"></path></svg>							46.5K						</div>
```

**Match count**: `1` (expected: 1)

| Dimension | Verdict | Finding |
|---|---|---|
| Stability | `ACCEPTABLE` | Selector uses a reasonably stable structural anchor. |
| Precision | `PRECISE` | Singleton selector resolves to exactly one node. |
| Accuracy | `NEEDS-CLEANING` | Numeric text includes words/symbols and must be normalized. |
| Robustness | `ROBUST` | Selector works on current template and degrades to empty list if field absent. |
| Reliability | `RELIABLE` | Value is present in rendered dump without interaction. |

**Overall grade**: `PASS`


---

### [Rumble] `comment_count_video` (code)

**Selector under audit:**
```css
#video-comments .comment-count
```

**Matched element in dump** (paste the raw outer HTML of the matched node, trimmed):
```html
<h3 class="comment-count">23 Comments </h3>
```

**Match count**: `1` (expected: 1)

| Dimension | Verdict | Finding |
|---|---|---|
| Stability | `ACCEPTABLE` | Selector uses a reasonably stable structural anchor. |
| Precision | `PRECISE` | Singleton selector resolves to exactly one node. |
| Accuracy | `NEEDS-CLEANING` | Numeric text includes words/symbols and must be normalized. |
| Robustness | `ROBUST` | Selector works on current template and degrades to empty list if field absent. |
| Reliability | `RELIABLE` | Value is present in rendered dump without interaction. |

**Overall grade**: `PASS`


---

### [BitChute] `video_container` (code)

**Selector under audit:**
```css
#video-card
```

**Matched element in dump** (paste the raw outer HTML of the matched node, trimmed):
```html
<div class="q-card q-card--flat no-shadow bg-transparent no-shadow no-border" dense="" id="video-card"><div class="q-card__section q-card__section--vert q-pa-none"><a class="q-item q-item-type row no-wrap q-item--clickable q-link cursor-pointer q-focusable q-hoverable q-py-none q-px-none" href="/video/KzK7T8QprVY" role="listitem" tabindex="0"><div class="q-focus-helper" tabindex="-1"></div><div aria-label="Video" class="q-img q-img--menu bc-border-radius" role="img"><div style="padding-bottom: 56.25%;"></div><div class="q-img__container absolute-full"><img alt="Video" aria-hidden="true" class="q-img__image q-img__image--with-transition q-img__image--loaded" draggable="false" fetchpriority="auto" loading="lazy" src="https://static-3.bitchute.com/live/cover_images/rfcShUDnIez0/KzK7T8QprVY_640x360.jpg" style="object-fit: cover; object-position: 50% 50%;"/></div><div class="q-img__content ab
```

**Match count**: `6` (expected: 6 (BitChute cards))

| Dimension | Verdict | Finding |
|---|---|---|
| Stability | `ACCEPTABLE` | Selector uses a reasonably stable structural anchor. |
| Precision | `PRECISE` | List selector matches 6 nodes in this dump. |
| Accuracy | `ACCURATE` | Matched node contains target value directly. |
| Robustness | `ROBUST` | Selector works on current template and degrades to empty list if field absent. |
| Reliability | `RELIABLE` | Value is present in rendered dump without interaction. |

**Overall grade**: `PASS`


---

### [BitChute] `video_url` (code)

**Selector under audit:**
```css
a[href*="/video/"]
```

**Matched element in dump** (paste the raw outer HTML of the matched node, trimmed):
```html
<a class="feature-video-title-link" data-v-1952597e="" href="/video/KzK7T8QprVY">What Ozempic is Doing to Your Liver</a>
```

**Match count**: `13` (expected: 6 (BitChute cards))

| Dimension | Verdict | Finding |
|---|---|---|
| Stability | `ACCEPTABLE` | Selector uses a reasonably stable structural anchor. |
| Precision | `PRECISE` | List selector matches 13 nodes in this dump. |
| Accuracy | `ACCURATE` | Matched node contains target value directly. |
| Robustness | `ROBUST` | Selector works on current template and degrades to empty list if field absent. |
| Reliability | `RELIABLE` | Value is present in rendered dump without interaction. |

**Overall grade**: `PASS`


---

### [BitChute] `video_title` (code)

**Selector under audit:**
```css
.q-item__label.bc-text-break.ellipsis-2-lines.bc-responsive-font
```

**Matched element in dump** (paste the raw outer HTML of the matched node, trimmed):
```html
<div class="q-item__label bc-text-break ellipsis-2-lines bc-responsive-font">What Ozempic is Doing to Your Liver <!-- --></div>
```

**Match count**: `6` (expected: 6 (BitChute cards))

| Dimension | Verdict | Finding |
|---|---|---|
| Stability | `FRAGILE` | Selector depends on styling classes. |
| Precision | `PRECISE` | List selector matches 6 nodes in this dump. |
| Accuracy | `ACCURATE` | Matched node contains target value directly. |
| Robustness | `ROBUST` | Selector works on current template and degrades to empty list if field absent. |
| Reliability | `RELIABLE` | Value is present in rendered dump without interaction. |

**Overall grade**: `PASS-WITH-NOTES`


---

### [BitChute] `video_views` (code)

**Selector under audit:**
```css
.absolute-bottom-left .text-caption
```

**Matched element in dump** (paste the raw outer HTML of the matched node, trimmed):
```html
<div class="text-caption">1,561</div>
```

**Match count**: `6` (expected: 6 (BitChute cards))

| Dimension | Verdict | Finding |
|---|---|---|
| Stability | `ACCEPTABLE` | Selector uses a reasonably stable structural anchor. |
| Precision | `PRECISE` | List selector matches 6 nodes in this dump. |
| Accuracy | `NEEDS-CLEANING` | Numeric text includes words/symbols and must be normalized. |
| Robustness | `ROBUST` | Selector works on current template and degrades to empty list if field absent. |
| Reliability | `RELIABLE` | Value is present in rendered dump without interaction. |

**Overall grade**: `PASS`


---

### [BitChute] `video_date` (code)

**Selector under audit:**
```css
.q-item__label.q-item__label--caption.text-caption
```

**Matched element in dump** (paste the raw outer HTML of the matched node, trimmed):
```html
<div class="q-item__label q-item__label--caption text-caption bc-text-break ellipsis"></div>
```

**Match count**: `18` (expected: 6 (BitChute cards))

| Dimension | Verdict | Finding |
|---|---|---|
| Stability | `FRAGILE` | Selector depends on styling classes. |
| Precision | `PRECISE` | List selector matches 18 nodes in this dump. |
| Accuracy | `NEEDS-CLEANING` | Relative display text requires parsing; machine-readable datetime is preferred when available. |
| Robustness | `ROBUST` | Selector works on current template and degrades to empty list if field absent. |
| Reliability | `RACE-RISK` | BitChute uses Vue hydration markers; early capture can return incomplete values. |

**Overall grade**: `REPLACE`

**Recommended replacement** *(only for REPLACE or CRITICAL grades)*:
```css
#video-card .q-item__label.q-item__label--caption.text-caption
```

**Why it is better**: The replacement narrows scope to the correct semantic region and reduces over-selection risk while preserving extraction reliability in rendered DOM.

**Extraction note**: `text()` unless attribute-specific (`attr(href)`, `attr(datetime)`, `attr(data-views)`).

**Normalization note**: Strip whitespace; parse abbreviated counts (`K/M/B`) and remove label suffixes.

---

### [BitChute] `about_description` (code)

**Selector under audit:**
```css
div[style*="white-space: pre-line;"]
```

**Matched element in dump** (paste the raw outer HTML of the matched node, trimmed):
```html
<div data-v-1952597e="" style="white-space: pre-line;">With over 43,000,000 followers worldwide, Dr. Eric Berg DC spreads the truth about getting healthy and losing weight. Dr. Berg, age 60, specializes in Healthy Keto® and Intermittent Fasting. He is the director of Dr. Berg's Nutritionals and a best-selling Amazon author.

His book, The Healthy Keto Plan describes specific strategies on doing the healthy version of the ketogenic diet as well as intermittent
fasting. He has conducted over 4800 seminars on health-related topics and trained over 2500 doctors world-wide in his methods. Dr. Berg breaks down confusing complex health topics into easy to understand, usable knowledge. 

For more information, go to our website at <a class="text-red-5" href="http://www.drberg.com" target="_blank">www.drberg.com</a> or call customer service at 703-354-7336. Much of the details of Dr. Berg's progra
```

**Match count**: `1` (expected: 1)

| Dimension | Verdict | Finding |
|---|---|---|
| Stability | `ACCEPTABLE` | Selector uses a reasonably stable structural anchor. |
| Precision | `PRECISE` | Singleton selector resolves to exactly one node. |
| Accuracy | `ACCURATE` | Matched node contains target value directly. |
| Robustness | `ROBUST` | Selector works on current template and degrades to empty list if field absent. |
| Reliability | `RELIABLE` | Value is present in rendered dump without interaction. |

**Overall grade**: `PASS`


---

### [BitChute] `about_details` (code)

**Selector under audit:**
```css
.q-item__label.text-bold
```

**Matched element in dump** (paste the raw outer HTML of the matched node, trimmed):
```html
<div class="q-item__label text-bold" data-v-1952597e="">204</div>
```

**Match count**: `5` (expected: N list items)

| Dimension | Verdict | Finding |
|---|---|---|
| Stability | `FRAGILE` | Selector depends on styling classes. |
| Precision | `PRECISE` | List selector matches 5 nodes in this dump. |
| Accuracy | `ACCURATE` | Matched node contains target value directly. |
| Robustness | `ROBUST` | Selector works on current template and degrades to empty list if field absent. |
| Reliability | `RELIABLE` | Value is present in rendered dump without interaction. |

**Overall grade**: `PASS-WITH-NOTES`


---

### [BitChute] `subscriber_count` (code)

**Selector under audit:**
```css
span[style*="cursor: pointer;"]
```

**Matched element in dump** (paste the raw outer HTML of the matched node, trimmed):
```html
<span data-v-1952597e="" style="cursor: pointer;">204 subscribers <!-- --></span>
```

**Match count**: `1` (expected: 1)

| Dimension | Verdict | Finding |
|---|---|---|
| Stability | `ACCEPTABLE` | Selector uses a reasonably stable structural anchor. |
| Precision | `PRECISE` | Singleton selector resolves to exactly one node. |
| Accuracy | `NEEDS-CLEANING` | Numeric text includes words/symbols and must be normalized. |
| Robustness | `ROBUST` | Selector works on current template and degrades to empty list if field absent. |
| Reliability | `RACE-RISK` | BitChute uses Vue hydration markers; early capture can return incomplete values. |

**Overall grade**: `REPLACE`

**Recommended replacement** *(only for REPLACE or CRITICAL grades)*:
```css
meta[property="og:title"]
```

**Why it is better**: The replacement narrows scope to the correct semantic region and reduces over-selection risk while preserving extraction reliability in rendered DOM.

**Extraction note**: `text()` unless attribute-specific (`attr(href)`, `attr(datetime)`, `attr(data-views)`).

**Normalization note**: Strip whitespace; parse abbreviated counts (`K/M/B`) and remove label suffixes.

---

### [BitChute] `video_comment_count` (code)

**Selector under audit:**
```css
span.item.count .value
```

**Matched element in dump** (paste the raw outer HTML of the matched node, trimmed):
```html
<span class="value">19</span>
```

**Match count**: `2` (expected: 1)

| Dimension | Verdict | Finding |
|---|---|---|
| Stability | `ACCEPTABLE` | Selector uses a reasonably stable structural anchor. |
| Precision | `OVER-SELECTS` | Singleton selector matches 2 nodes and is ambiguous. |
| Accuracy | `NEEDS-CLEANING` | Numeric text includes words/symbols and must be normalized. |
| Robustness | `TEMPLATE-DEPENDENT` | Broad selector is sensitive to layout/template variation. |
| Reliability | `RELIABLE` | Value is present in rendered dump without interaction. |

**Overall grade**: `REPLACE`

**Recommended replacement** *(only for REPLACE or CRITICAL grades)*:
```css
span.item.count .value:first-of-type
```

**Why it is better**: The replacement narrows scope to the correct semantic region and reduces over-selection risk while preserving extraction reliability in rendered DOM.

**Extraction note**: `text()` unless attribute-specific (`attr(href)`, `attr(datetime)`, `attr(data-views)`).

**Normalization note**: Strip whitespace; parse abbreviated counts (`K/M/B`) and remove label suffixes.

---

## Cross-Cutting Checks

### CC1 ? Fallback Chain Coverage
- Coverage gap: BitChute `video_date` primary over-selects and currently relies on in-loop filtering; add scoped fallback `#video-card .q-item__label.q-item__label--caption.text-caption` plus regex relative-date parse.
- Coverage gap: BitChute `video_comment_count` on video page can over-select; add ordered fallback chain with strict container scoping.
- Rumble comment count on cards is partial (21/28); current code already falls back to video-page fetch, so no silent-None gap.

### CC2 ? Selector Collision Check
- Collision risk confirmed: BitChute `a[href*="/video/"]` matches links beyond card scope; scope to `#video-card a[href*="/video/"]`.
- Collision risk confirmed: BitChute broad `span` for total videos collides with unrelated spans.
- Rumble `external_links` and `video_urls` do not collide when scoped to About socials vs card links.

### CC3 ? Static vs JS-Rendered Coverage

| Field | Platform | Selector type | Static or JS? | Static fallback exists? |
|---|---|---|---|---|
| channel_name | BitChute | div.text-bold.text-h4 / meta[og:title] | JS+Static | Yes |
| subscriber_count | BitChute | span[style*="cursor: pointer;"] | JS-hydrated | Partial |
| video_upload_dates | BitChute | .q-item__label...text-caption | JS text | No datetime fallback |
| channel_name | Rumble | .channel-header--title h1 | Static | Yes |
| subscriber_count | Rumble | .channel-header--title span span | Static | Yes |
| video_upload_dates | Rumble | time.videostream__time[datetime] | Static | Yes |
| view_count(video) | Rumble | .media-description-info-views / json_ld | Static | Yes |

Single points of failure: BitChute upload-date extraction (no machine-readable attribute in dump), and BitChute subscriber count when hydration stalls.

### CC4 ? `mailto:` Email Extraction Gap
- BitChute about dump `mailto:` links found: 0; Rumble about dump `mailto:` links found: 0.
- Current strategy should still include `a[href^="mailto:"]` selector in fallback chain; regex-only extraction is insufficient when link text is not the address.

### CC5 ? Date Field Machine-Readability
- Rumble card dates: `time[datetime]` present (28 nodes) and should be primary.
- BitChute card/video dates: `time[datetime]` not present in dumps (home=0, video=0); relative text parsing is required.
- Rumble video page includes JSON-LD VideoObject: True (use `uploadDate` fallback).

## Executive Summary
Audited 40 selectors (manual + code) against six rendered dumps. 35 selectors graded PASS/PASS-WITH-NOTES, 5 graded REPLACE, and 0 graded CRITICAL. The largest reliability risk is BitChute JS-hydrated fields (subscriber and some metadata) that can race before hydration. The largest stability risk is heavy dependence on presentational BEM/Quasar class names on both platforms. Rumble card date extraction is in strong shape because `time[datetime]` is consistently present. BitChute date extraction remains inherently weaker because only relative display text is available in the dump. Card-scoped selector tightening removes the highest-variance collision risks immediately. Existing Rumble video-page fallbacks materially reduce data-loss risk when per-card comments are missing.

## Priority Fix List
| Priority | Platform | Field | Current Grade | Failure Dimensions | Fix Effort |
|---|---|---|---|---|---|
| 1 | BitChute | video_upload_dates | REPLACE | Precision, Reliability | Medium |
| 2 | BitChute | video_url | REPLACE | Precision, Robustness | Low |
| 3 | BitChute | video_comment_count (video page) | REPLACE | Precision | Low |
| 4 | BitChute | total_videos | REPLACE | Precision, Robustness | Low |
| 5 | Rumble | video_comment_counts (card-level partial) | PASS-WITH-NOTES | Robustness | Medium |

## Production-Ready Selector Constants
```python
# =============================================================
# BITCHUTE ? CHANNEL PAGE SELECTORS
# Last audited: 2026-05-25
# Dump source: Bitchute home/about/video tab html dump
# =============================================================
BITCHUTE_CHANNEL = {
    "channel_name": {"primary": "meta[property='og:title']", "fallbacks": ["div.text-bold.text-h4", "h1"], "extract": "attr(content)", "normalize": "strip_title_suffix()", "js_required": False},
    "channel_description": {"primary": "div[style*='white-space: pre-line;']", "fallbacks": ["meta[property='og:description']", "meta[name='description']"], "extract": "text()", "normalize": "strip()", "js_required": True},
    "subscriber_count": {"primary": "span[style*='cursor: pointer;']", "fallbacks": ["#subscriber_count", "[id*='subscriber']"], "extract": "text()", "normalize": "parse_count_abbreviation()", "js_required": True, "static_fallback": "meta[property='og:description']"},
    "video_card": {"primary": "#video-card", "fallbacks": [], "extract": "node", "normalize": "none", "js_required": True},
    "video_titles": {"primary": "#video-card .q-item__label.bc-text-break.ellipsis-2-lines.bc-responsive-font", "fallbacks": ["#video-card a[href*='/video/']"], "extract": "text()", "normalize": "strip()", "js_required": True},
    "video_view_counts": {"primary": "#video-card .absolute-bottom-left .text-caption", "fallbacks": ["#video-card [aria-label*='view']"], "extract": "text()", "normalize": "parse_int_commas()", "js_required": True},
    "video_upload_dates": {"primary": "#video-card .q-item__label.q-item__label--caption.text-caption", "fallbacks": ["regex:(\d+\s+(second|minute|hour|day|week|month|year)s?\s+ago|yesterday|just now)"], "extract": "text()", "normalize": "parse_relative_datetime()", "js_required": True},
    "video_urls": {"primary": "#video-card a[href*='/video/']", "fallbacks": ["a[href*='/video/']"], "extract": "attr(href)", "normalize": "urljoin(base) + dedupe", "js_required": True},
    "external_links": {"primary": "div[style*='white-space: pre-line;'] a[href^='http']", "fallbacks": ["a[href^='http']"], "extract": "attr(href)", "normalize": "exclude_bitchute_domain", "js_required": True},
    "email_addresses": {"primary": "a[href^='mailto:']", "fallbacks": ["regex:[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}"], "extract": "href_text", "normalize": "lowercase+dedupe", "js_required": False},
}

BITCHUTE_VIDEO = {
    "view_count": {"primary": "[class*='view']", "fallbacks": ["meta[itemprop='interactionCount']"], "extract": "text()", "normalize": "parse_count_abbreviation()", "js_required": True},
    "comment_count": {"primary": "span.item.count .value:first-of-type", "fallbacks": ["#comments span.value", "regex:(\d+)\s+comments?"], "extract": "text()", "normalize": "int", "js_required": True},
    "upload_date": {"primary": "regex:(\d+\s+(second|minute|hour|day|week|month|year)s?\s+ago|yesterday|just now)", "fallbacks": [], "extract": "regex", "normalize": "parse_relative_datetime()", "js_required": True},
}

# =============================================================
# RUMBLE ? CHANNEL PAGE SELECTORS
# Last audited: 2026-05-25
# Dump source: Rumble all/about/video tab html dump
# =============================================================
RUMBLE_CHANNEL = {
    "channel_name": {"primary": ".channel-header--title h1", "fallbacks": ["meta[property='og:title']"], "extract": "text()", "normalize": "strip()", "js_required": False},
    "channel_description": {"primary": ".channel-about--description > p", "fallbacks": ["meta[property='og:description']"], "extract": "text()", "normalize": "strip()", "js_required": False},
    "subscriber_count": {"primary": ".channel-header--title span span", "fallbacks": ["meta[property='og:description']"], "extract": "text()", "normalize": "parse_count_abbreviation()", "js_required": False},
    "video_card": {"primary": "div.videostream.thumbnail__grid--item", "fallbacks": [], "extract": "node", "normalize": "none", "js_required": False},
    "video_titles": {"primary": "div.videostream.thumbnail__grid--item h3.thumbnail__title", "fallbacks": ["h3.thumbnail__title.line-clamp-2"], "extract": "text()", "normalize": "strip()", "js_required": False},
    "video_view_counts": {"primary": "div.videostream.thumbnail__grid--item span.videostream__views[data-views]", "fallbacks": ["span.videostream__views--count"], "extract": "attr(data-views)", "normalize": "int", "js_required": False},
    "video_comment_counts": {"primary": "div.videostream.thumbnail__grid--item span.videostream__comments--count", "fallbacks": ["div.videostream.thumbnail__grid--item span.videostream__comments", "video-page fallback"], "extract": "text()", "normalize": "int", "js_required": False},
    "video_upload_dates": {"primary": "div.videostream.thumbnail__grid--item time.videostream__time", "fallbacks": ["div.videostream.thumbnail__grid--item time[datetime]"], "extract": "attr(datetime)", "normalize": "datetime.fromisoformat", "js_required": False},
    "video_urls": {"primary": "div.videostream.thumbnail__grid--item a.videostream__link[href*='/v']", "fallbacks": ["a[href*='/v']"], "extract": "attr(href)", "normalize": "urljoin(base)+canonicalize", "js_required": False},
    "external_links": {"primary": ".channel-about--socials a.channel-about--socials-item[href^='http']", "fallbacks": [".channel-about a[href^='http']"], "extract": "attr(href)", "normalize": "exclude_rumble_domain", "js_required": False},
    "email_addresses": {"primary": "a[href^='mailto:']", "fallbacks": ["regex:[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}"], "extract": "href_text", "normalize": "lowercase+dedupe", "js_required": False},
}

RUMBLE_VIDEO = {
    "view_count": {"primary": ".media-description-info-views", "fallbacks": ["meta[itemprop='interactionCount']"], "extract": "text()", "normalize": "parse_count_abbreviation()", "js_required": False},
    "comment_count": {"primary": "#video-comments .comment-count", "fallbacks": ["[class*='comment-count']"], "extract": "text()", "normalize": "int", "js_required": False},
    "upload_date": {"primary": "script[type='application/ld+json']", "fallbacks": [".media-description-time-views-container [title]"], "extract": "json_ld(uploadDate)", "normalize": "datetime parse", "js_required": False},
}
```