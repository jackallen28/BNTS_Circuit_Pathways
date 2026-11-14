// Party Lights: a web page made with ArduinoPath's Web Page Designer.
// On a phone, join the WiFi called "PartyLights", then open the address in the Serial Monitor.

#define RGB_RED 25
#define RGB_GREEN 26
#define RGB_BLUE 27
#define BUZZER_PIN 33

#include <WiFi.h>
#include <WebServer.h>

// ---- 1. WiFi ----
const char* WIFI_NAME = "PartyLights";
const char* WIFI_PASSWORD = "circuit123";  // at least 8 characters

WebServer server(80);

// ---- 2. What the page remembers and shows (change readings in loop) ----
String lightColour = "#ff00aa";
int beepPitch = 0;

// ---- 3. The page ----
const char PAGE[] = R"(<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Party Lights</title>
<style>
  body { font-family: sans-serif; margin: 0; padding: 16px; background: #111827; color: #f3f4f6; text-align: center; }
  main { max-width: 420px; margin: 0 auto; padding: 16px; border-radius: 16px; background: #1f2937; }
  h1 { color: #22d3ee; }
  .btn { display: inline-block; min-width: 60%; padding: 14px 20px; border: 0; border-radius: 999px; background: #22d3ee; color: #0b1220; font-size: 1.2em; text-decoration: none; }
  input[type=range], meter { width: 90%; }
  input[type=color] { width: 80px; height: 48px; border: 0; }
  .reading b { font-size: 1.6em; color: #22d3ee; }
  .switch { color: inherit; text-decoration: none; font-size: 1.2em; }
  .switch .track { display: inline-block; vertical-align: middle; width: 52px; height: 28px; border-radius: 14px; background: #bbb; position: relative; }
  .switch .knob { position: absolute; top: 3px; left: 3px; width: 22px; height: 22px; border-radius: 50%; background: #fff; }
  .switch.sw-on .track { background: #22d3ee; }
  .switch.sw-on .knob { left: 27px; }
  .switch b { text-transform: uppercase; }
  .status .dot { display: inline-block; width: 16px; height: 16px; border-radius: 50%; background: #bbb; vertical-align: middle; }
  .status.st-on .dot { background: #34c759; box-shadow: 0 0 8px #34c759; }
</style>
</head>
<body>
<main>
  <h1>Party Lights</h1>
  <p>Pick a colour for the party.</p>
  <form action="/set-light-colour">
    <label>Light colour<br><input type="color" name="value" value="%lightColour%"></label>
    <button class="btn">Set</button>
  </form>
  <form action="/beep-pitch">
    <label>Beep pitch <b>%beepPitch%</b><br><input type="range" name="value" min="0" max="2000" value="%beepPitch%"></label>
    <button class="btn">Set</button>
  </form>
  <p><a class="btn" href="/beep">Beep!</a></p>
</main>
</body>
</html>
)";

// The page, with today's numbers put in where %name% is.
String page() {
  String html = PAGE;
  html.replace("%lightColour%", lightColour);
  html.replace("%beepPitch%", String(beepPitch));
  return html;
}

void showPage() {
  server.send(200, "text/html", page());
}

// A colour like #ff8000 is three numbers in hexadecimal: red ff, green 80, blue 00.
int hexValue(String colour, int at) {
  int v = 0;
  for (int i = at; i < at + 2; i++) {
    char c = colour.charAt(i);
    v = v * 16 + (c >= 'a' ? c - 'a' + 10 : (c >= 'A' ? c - 'A' + 10 : c - '0'));
  }
  return v;
}

// ---- 4. What happens when someone uses the page ----
void setLightColour() {
  lightColour = server.arg("value");
  analogWrite(RGB_RED, hexValue(lightColour, 1));
  analogWrite(RGB_GREEN, hexValue(lightColour, 3));
  analogWrite(RGB_BLUE, hexValue(lightColour, 5));
  Serial.print("Light colour: ");
  Serial.println(lightColour);
  showPage();
}

void setBeepPitch() {
  beepPitch = server.arg("value").toInt();
  if (beepPitch > 0) tone(BUZZER_PIN, beepPitch);  // a higher number is a higher note
  else noTone(BUZZER_PIN);
  Serial.print("Beep pitch: ");
  Serial.println(beepPitch);
  showPage();
}

void beep() {
  tone(BUZZER_PIN, 880, 300);  // 880 beats a second, for 300 ms
  Serial.println("Beep! was pressed");
  showPage();
}

void setup() {
  Serial.begin(115200);
  pinMode(RGB_RED, OUTPUT);
  pinMode(RGB_GREEN, OUTPUT);
  pinMode(RGB_BLUE, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  WiFi.softAP(WIFI_NAME, WIFI_PASSWORD);
  server.on("/", showPage);
  server.on("/set-light-colour", setLightColour);
  server.on("/beep-pitch", setBeepPitch);
  server.on("/beep", beep);
  server.begin();
  Serial.print("Open http://");
  Serial.println(WiFi.softAPIP());
}

void loop() {
  server.handleClient();
}
