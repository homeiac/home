// Compare every rendered OCR tag and highlight against the independent Immich readback.
export async function checkOcrTags(page, ocr) {
  return page.$$eval('article[id]', (cards, expected) => {
    let clicks = 0;
    for (const card of cards) {
      const regions = expected[card.id];
      const details = card.querySelector('.ocr-tags');
      if (Boolean(regions.length) !== Boolean(details)) throw Error('Missing or unexpected OCR tags');
      if (!details) continue;
      details.open = true;
      const buttons = Array.from(details.querySelectorAll('button'));
      if (buttons.length !== regions.length) throw Error('Incorrect OCR region count');
      for (const [index, button] of buttons.entries()) {
        const region = regions[index];
        if (button.dataset.immichOcrId !== region.id || button.textContent !== region.text)
          throw Error('Incorrect OCR tag, text or reading order');
        button.click();
        const overlay = card.querySelector('figure .ocr-region');
        if (overlay?.dataset.immichOcrId !== region.id) throw Error('Incorrect selected OCR region');
        const coords = overlay.style.clipPath.match(/[+-]?[\d.]+(?:e[+-]?\d+)?(?=%)/gi).map(Number);
        if (coords.length !== 8 || coords.some((v, i) => Math.abs(v / 100 - region.polygon[i]) > 0.00001))
          throw Error('Incorrect OCR highlight geometry');
        clicks++;
      }
      details.open = false;
    }
    return clicks;
  }, ocr);
}
