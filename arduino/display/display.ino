/*
 * Backseat Driver — Arduino Display
 * UNO R4 WiFi + Elegoo 2.8" ILI9341 TFT Shield (240x320)
 *
 * Receives compact JSON over USB serial from bridge.py:
 *   {"opt_spd":38.5,"opt_rpm":2450,"cur_spd":42.1,"action":"coast","eco":85,
 *    "lat":38.5449,"lon":-121.7405}
 *   opt_spd / cur_spd are already in mph (converted by the backend from phone
 * GPS m/s).
 *
 * Background color encodes speed delta (current vs. optimal):
 *   Red    → going too fast, ease off  (delta > +5 mph)
 *   Orange → slightly fast             (delta +2..+5 mph)
 *   Dark   → on target                 (delta -2..+2 mph)
 *   Cyan   → slightly slow             (delta -5..-2 mph)
 *   Blue   → need to speed up a lot    (delta < -5 mph)
 *
 * Libraries needed (Arduino Library Manager):
 *   - GFX Library for Arduino (Moon On Our Nation)
 *   - ArduinoJson (Benoit Blanchon, v7+)
 */

#include <ArduinoJson.h>
#include <Arduino_GFX_Library.h>

// ── Hardware ────────────────────────────────────────────────────────────────
Arduino_DataBus *bus = new Arduino_UNOPAR8();
Arduino_GFX *gfx = new Arduino_ILI9341(bus, A4);

// ── Color Palette (RGB565) ───────────────────────────────────────────────────
#define BLACK 0x0000
#define WHITE 0xFFFF
#define LIGHT_GRAY 0xC618
#define DARK_GRAY 0x18C3

// Background zone colors
#define BG_RED 0x9000      // deep red   — too fast
#define BG_ORANGE 0x9400   // dark orange — slightly fast
#define BG_NEUTRAL 0x0C0C  // very dark teal — on target
#define BG_CYAN_DIM 0x0449 // dim cyan — slightly slow
#define BG_BLUE 0x000D     // deep blue — too slow

// Text accent colors
#define ACCENT_SPEED 0xFFFF // white — primary metric
#define ACCENT_RPM 0x07FF   // cyan — secondary metric
#define ACCENT_DIM 0x7BEF   // gray — labels

// ── State ────────────────────────────────────────────────────────────────────
float lastOptSpd = -9999.0f;
float lastOptRpm = -9999.0f;
float lastCurSpd = -9999.0f;
char lastAction[16] = "";
int lastEco = -1;
float lastLat = -9999.0f;
float lastLon = -9999.0f;
uint16_t lastBg = 0xFFFF; // force first draw
unsigned long lastPacketMs = 0;

// ── Background color selection
// ────────────────────────────────────────────────
uint16_t bgForDelta(float delta) {
  if (delta > 5.0f)
    return BG_RED;
  if (delta > 2.0f)
    return BG_ORANGE;
  if (delta < -5.0f)
    return BG_BLUE;
  if (delta < -2.0f)
    return BG_CYAN_DIM;
  return BG_NEUTRAL;
}

// ── Helpers
// ───────────────────────────────────────────────────────────────────
void fillBg(uint16_t color) {
  if (color == lastBg)
    return;
  gfx->fillScreen(color);
  lastBg = color;
  // Force all fields to redraw against new background
  lastOptSpd = -9999.0f;
  lastOptRpm = -9999.0f;
  lastCurSpd = -9999.0f;
  lastAction[0] = '\0';
  lastEco = -1;
  lastLat = -9999.0f;
  lastLon = -9999.0f;
}

// Draw a centered string in a bounding box (clears area first)
void drawCentered(int x, int y, int w, int h, const char *text, int textSize,
                  uint16_t color, uint16_t bg) {
  gfx->fillRect(x, y, w, h, bg);
  gfx->setTextSize(textSize);
  gfx->setTextColor(color);
  int charW = 6 * textSize;
  int textPx = strlen(text) * charW;
  int cx = x + (w - textPx) / 2;
  int cy = y + (h - 8 * textSize) / 2;
  if (cx < x)
    cx = x;
  gfx->setCursor(cx, cy);
  gfx->print(text);
}

// Draw a small label (no clearing — called after fillBg or on static redraws)
void drawLabel(int x, int y, const char *text, uint16_t bg) {
  gfx->setTextSize(2);
  gfx->setTextColor(ACCENT_DIM);
  gfx->fillRect(x, y, 240 - x * 2, 20, bg);
  gfx->setCursor(x, y);
  gfx->print(text);
}

// ── Section divider line
// ──────────────────────────────────────────────────────
void drawDivider(int y, uint16_t bg) {
  uint16_t lineColor = (bg == BG_NEUTRAL || bg == BG_CYAN_DIM || bg == BG_BLUE)
                           ? 0x0C8C  // lighter teal
                           : 0x5800; // dark amber
  gfx->drawFastHLine(20, y, 200, lineColor);
}

// ── Full UI redraw (called on bg change or startup)
// ───────────────────────────
void redrawLayout(uint16_t bg) {
  // Section 1: Suggested Speed
  drawLabel(12, 8, "SUGGESTED SPEED", bg);
  drawDivider(162, bg);

  // Section 2: Target RPM
  drawLabel(12, 170, "TARGET RPM", bg);
  drawDivider(240, bg);

  // Section 3: GPS Coordinates
  drawLabel(12, 248, "GPS", bg);
  drawDivider(290, bg);

  // Section 4: Current state footer
  drawLabel(12, 298, "CURRENT", bg);
}

// ── Value updaters
// ─────────────────────────────────────────────────────────────
void updateOptSpeed(float v, uint16_t bg) {
  if (v == lastOptSpd)
    return;
  char buf[12];
  snprintf(buf, sizeof(buf), "%.1f", v);
  // Big number (textSize 7 ≈ 42px wide per char)
  drawCentered(0, 28, 240, 76, buf, 7, ACCENT_SPEED, bg);
  // "mph" unit
  drawCentered(0, 106, 240, 20, "mph", 2, ACCENT_DIM, bg);
  lastOptSpd = v;
}

void updateOptRpm(float v, uint16_t bg) {
  if (v == lastOptRpm)
    return;
  char buf[12];
  snprintf(buf, sizeof(buf), "%d", (int)v);
  drawCentered(0, 186, 240, 50, buf, 5, ACCENT_RPM, bg);
  lastOptRpm = v;
}

void updateGPS(float lat, float lon, uint16_t bg) {
  // Only redraw if values changed by more than 0.00001 deg (~1m)
  if (fabs(lat - lastLat) < 0.00001f && fabs(lon - lastLon) < 0.00001f)
    return;

  char latBuf[20], lonBuf[20];
  // Show 6 decimal places — ~11 cm precision
  dtostrf(lat, 10, 6, latBuf);
  dtostrf(lon, 11, 6, lonBuf);

  // Trim leading spaces
  char latLine[24], lonLine[24];
  snprintf(latLine, sizeof(latLine), "LAT %s", latBuf + strspn(latBuf, " "));
  snprintf(lonLine, sizeof(lonLine), "LON %s", lonBuf + strspn(lonBuf, " "));

  gfx->fillRect(0, 256, 240, 16, bg);
  gfx->setTextSize(1);
  gfx->setTextColor(ACCENT_RPM); // cyan — same accent as RPM
  gfx->setCursor(12, 258);
  gfx->print(latLine);

  gfx->fillRect(0, 274, 240, 16, bg);
  gfx->setCursor(12, 276);
  gfx->print(lonLine);

  lastLat = lat;
  lastLon = lon;
}

void updateCurrentState(float curSpd, const char *action, int eco,
                        uint16_t bg) {
  bool changed = (curSpd != lastCurSpd) || (strcmp(action, lastAction) != 0) ||
                 (eco != lastEco);
  if (!changed)
    return;

  // Current speed
  char speedBuf[8];
  snprintf(speedBuf, sizeof(speedBuf), "%.1f", curSpd);

  // Action label — uppercase, max 10 chars
  char actBuf[16];
  strncpy(actBuf, action, sizeof(actBuf) - 1);
  actBuf[sizeof(actBuf) - 1] = '\0';
  for (int i = 0; actBuf[i]; i++)
    actBuf[i] = toupper(actBuf[i]);

  // Eco score
  char ecoBuf[8];
  snprintf(ecoBuf, sizeof(ecoBuf), "%d%%", eco);

  // Compose footer: "42.1 mph  COAST  ECO 85%"
  char footer[48];
  snprintf(footer, sizeof(footer), "%s mph  %s  ECO %s", speedBuf, actBuf,
           ecoBuf);

  gfx->fillRect(0, 306, 240, 14, bg);
  gfx->setTextSize(1);
  gfx->setTextColor(WHITE);
  int len = strlen(footer);
  int cx = (240 - len * 6) / 2;
  if (cx < 2)
    cx = 2;
  gfx->setCursor(cx, 308);
  gfx->print(footer);

  lastCurSpd = curSpd;
  strncpy(lastAction, action, sizeof(lastAction) - 1);
  lastEco = eco;
}

void drawNoData() {
  gfx->fillScreen(DARK_GRAY);
  lastBg = DARK_GRAY;
  gfx->setTextColor(LIGHT_GRAY);
  gfx->setTextSize(2);
  gfx->setCursor(50, 140);
  gfx->print("NO DATA");
  gfx->setCursor(30, 165);
  gfx->print("waiting for API...");
}

// ── Arduino entry points
// ───────────────────────────────────────────────────────
void setup() {
  Serial.begin(115200);
  gfx->begin();
  gfx->setRotation(0); // Portrait
  drawNoData();
}

void loop() {
  if (Serial.available()) {
    String line = Serial.readStringUntil('\n');
    line.trim();
    if (line.length() == 0)
      return;

    JsonDocument doc;
    DeserializationError err = deserializeJson(doc, line);
    if (err)
      return;

    // opt_spd / cur_spd arrive already in mph from bridge.py — no conversion
    // needed
    float optSpd = doc["opt_spd"] | 0.0f;
    float optRpm = doc["opt_rpm"] | 0.0f;
    float curSpd = doc["cur_spd"] | 0.0f;
    int eco = doc["eco"] | 0;
    const char *action = doc["action"] | "maintain";
    float lat = doc["lat"] | 0.0f;
    float lon = doc["lon"] | 0.0f;

    float delta = curSpd - optSpd;
    uint16_t bg = bgForDelta(delta);

    // Repaint background if zone changed
    fillBg(bg);

    // Redraw labels (after potential background fill)
    redrawLayout(bg);

    // Redraw values
    updateOptSpeed(optSpd, bg);
    updateOptRpm(optRpm, bg);
    if (lat != 0.0f || lon != 0.0f)
      updateGPS(lat, lon, bg);
    updateCurrentState(curSpd, action, eco, bg);

    lastPacketMs = millis();
  }

  // Timeout — no data for 3 seconds
  if (lastPacketMs != 0 && millis() - lastPacketMs > 3000) {
    lastPacketMs = 0;
    lastBg = 0xFFFF; // force full redraw next time
    drawNoData();
  }
}
