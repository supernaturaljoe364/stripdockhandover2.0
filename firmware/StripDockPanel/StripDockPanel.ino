// StripDock purifier control panel - Arduino Nano / Uno
// Wiring: OLED SSD1306 I2C  VCC->5V, GND->GND, SDA->A4, SCL->A5
//         Amber LED (HOLD)   D3 -> 330R -> LED long leg, short leg -> GND
//         Green LED (CONFIRM) D4 -> 330R -> LED long leg, short leg -> GND
//         Push button        D2 -> button -> GND (internal pull-up)
// Library: "U8g2" by olikraus (Library Manager)
//
// Serial 115200, one command per line (Serial Monitor: "Newline"):
//   HOLD     -> latch RO+UV hold (saved in EEPROM, survives power loss)
//   PASS     -> a passing re-test; if held, asks for CONFIRM within 60 s
//   UNKNOWN  -> bad/uncertain reading; never clears a hold
//   PING     -> laptop heartbeat (send every ~2 s)
//   STATUS   -> report state
// Every command gets the reply "OK <STATE>". Events start with "EVT".
// A brand-new board (blank EEPROM) starts in HOLD: unknown memory = cautious.

#include <Arduino.h>
#include <EEPROM.h>
#include <Wire.h>
#include <U8x8lib.h>

const uint8_t PIN_BTN = 2;
const uint8_t PIN_AMBER = 3;
const uint8_t PIN_GREEN = 4;
const int EE_ADDR = 0;
const unsigned long CONFIRM_MS = 60000UL;
const unsigned long LINK_MS = 10000UL;
const unsigned long DEBOUNCE_MS = 40UL;

// If the OLED stays blank and an I2C scan shows 0x3D, set this to 0x3D.
const uint8_t OLED_ADDR = 0x3C;

U8X8_SSD1306_128X64_NONAME_HW_I2C oled(U8X8_PIN_NONE);

enum State : uint8_t { ADAPTIVE, HELD, CONFIRM_WAIT };
State state = HELD;
bool lastUnknown = false;
bool linkLost = true;
bool dirty = true;
unsigned long lastMsgMs = 0;
unsigned long confirmStartMs = 0;

char buf[24];
uint8_t blen = 0;

int btnStable = HIGH;
int btnLast = HIGH;
unsigned long btnChangeMs = 0;

void saveHold(bool h) {
  uint8_t v = h ? 1 : 0;
  if (EEPROM.read(EE_ADDR) != v) EEPROM.write(EE_ADDR, v);  // write only on change
}

bool loadHold() {
  return EEPROM.read(EE_ADDR) != 0;  // 1 or blank (0xFF) -> hold
}

const char* stateName() {
  switch (state) {
    case ADAPTIVE: return "ADAPTIVE";
    case HELD: return "HOLD";
    default: return "CONFIRM_WAIT";
  }
}

void updateLeds() {
  digitalWrite(PIN_AMBER, state == ADAPTIVE ? LOW : HIGH);   // held until cleared
  digitalWrite(PIN_GREEN, state == CONFIRM_WAIT ? HIGH : LOW);
}

void draw() {
  oled.clearDisplay();
  oled.setFont(u8x8_font_chroma48medium8_r);
  oled.drawString(0, 0, "StripDock panel");
  if (state == ADAPTIVE) {
    oled.draw2x2String(0, 2, "ADAPTIVE");
    oled.drawString(0, 5, "TDS logic active");
  } else if (state == HELD) {
    oled.draw2x2String(0, 2, "HOLD");
    oled.drawString(0, 5, "Mode: RO+UV");
  } else {
    oled.draw2x2String(0, 2, "CONFIRM?");
    oled.drawString(0, 5, "Press btn <60s");
  }
  if (lastUnknown) oled.drawString(0, 6, "UNKNOWN-retest");
  oled.drawString(0, 7, linkLost ? "LINK LOST" : "Link OK");
  updateLeds();
  dirty = false;
}

void reply() {
  Serial.print(F("OK "));
  Serial.println(stateName());
}

void handleCommand(char* cmd) {
  for (char* p = cmd; *p; ++p) *p = toupper(*p);
  lastMsgMs = millis();
  if (linkLost) { linkLost = false; dirty = true; }

  if (strcmp(cmd, "HOLD") == 0) {
    state = HELD;
    saveHold(true);
    lastUnknown = false;
    dirty = true;
    reply();
  } else if (strcmp(cmd, "PASS") == 0) {
    lastUnknown = false;
    if (state != ADAPTIVE) {
      state = CONFIRM_WAIT;           // hold stays saved until the button is pressed
      confirmStartMs = millis();
    }
    dirty = true;
    reply();
  } else if (strcmp(cmd, "UNKNOWN") == 0) {
    lastUnknown = true;
    if (state == CONFIRM_WAIT) state = HELD;  // an unknown re-test cancels the confirm
    dirty = true;
    reply();
  } else if (strcmp(cmd, "PING") == 0 || strcmp(cmd, "STATUS") == 0) {
    reply();
  } else if (cmd[0] != '\0') {
    Serial.print(F("ERR unknown command: "));
    Serial.println(cmd);
  }
}

void readSerial() {
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      if (blen > 0) {
        buf[blen] = '\0';
        handleCommand(buf);
        blen = 0;
      }
    } else if (blen < sizeof(buf) - 1) {
      buf[blen++] = c;
    }
  }
}

void readButton() {
  int r = digitalRead(PIN_BTN);
  if (r != btnLast) { btnLast = r; btnChangeMs = millis(); }
  if (millis() - btnChangeMs > DEBOUNCE_MS && r != btnStable) {
    btnStable = r;
    if (btnStable == LOW) {  // pressed
      if (state == CONFIRM_WAIT) {
        state = ADAPTIVE;
        saveHold(false);
        lastUnknown = false;
        dirty = true;
        Serial.println(F("EVT CLEARED"));
      } else {
        Serial.println(F("EVT BUTTON_IGNORED"));
      }
    }
  }
}

void setup() {
  pinMode(PIN_BTN, INPUT_PULLUP);
  pinMode(PIN_AMBER, OUTPUT);
  pinMode(PIN_GREEN, OUTPUT);
  Serial.begin(115200);
  oled.setI2CAddress(OLED_ADDR * 2);
  oled.begin();
  oled.setPowerSave(0);
  state = loadHold() ? HELD : ADAPTIVE;
  draw();
  Serial.print(F("READY "));
  Serial.println(stateName());
}

void loop() {
  readSerial();
  readButton();

  if (state == CONFIRM_WAIT && millis() - confirmStartMs > CONFIRM_MS) {
    state = HELD;
    dirty = true;
    Serial.println(F("EVT CONFIRM_TIMEOUT"));
  }
  if (!linkLost && millis() - lastMsgMs > LINK_MS) {
    linkLost = true;
    dirty = true;
  }
  if (dirty) draw();
}
