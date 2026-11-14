// Plant Buddy: a web page made with ArduinoPath's Web Page Designer.
// On a phone, join the WiFi called "PlantBuddy", then open the address in the Serial Monitor.

#define LED_PIN 25
#define SOIL_PIN 36

#include <WiFi.h>
#include <WebServer.h>

// ---- 1. WiFi ----
const char* WIFI_NAME = "PlantBuddy";
const char* WIFI_PASSWORD = "circuit123";  // at least 8 characters

WebServer server(80);

// ---- 2. What the page remembers and shows (change readings in loop) ----
bool ledPinOn = false;  // is LED_PIN on?
int soil = 0;

// ---- 3. The page ----
const char PAGE[] = R"(<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="5">
<title>Plant Buddy</title>
<style>
  body { font-family: sans-serif; margin: 0; padding: 16px; background: #e8fbfc; color: #08363a; text-align: center; }
  main { max-width: 420px; margin: 0 auto; padding: 16px; border-radius: 16px; background: #ffffff; }
  h1 { color: #19c1ca; }
  .btn { display: inline-block; min-width: 60%; padding: 14px 20px; border: 0; border-radius: 999px; background: #19c1ca; color: #ffffff; font-size: 1.2em; text-decoration: none; }
  input[type=range], meter { width: 90%; }
  input[type=color] { width: 80px; height: 48px; border: 0; }
  .reading b { font-size: 1.6em; color: #19c1ca; }
  .switch { color: inherit; text-decoration: none; font-size: 1.2em; }
  .switch .track { display: inline-block; vertical-align: middle; width: 52px; height: 28px; border-radius: 14px; background: #bbb; position: relative; }
  .switch .knob { position: absolute; top: 3px; left: 3px; width: 22px; height: 22px; border-radius: 50%; background: #fff; }
  .switch.sw-on .track { background: #19c1ca; }
  .switch.sw-on .knob { left: 27px; }
  .switch b { text-transform: uppercase; }
  .status .dot { display: inline-block; width: 16px; height: 16px; border-radius: 50%; background: #bbb; vertical-align: middle; }
  .status.st-on .dot { background: #34c759; box-shadow: 0 0 8px #34c759; }
</style>
</head>
<body>
<main>
  <h1>Plant Buddy</h1>
  <h2>How is my plant?</h2>
  <p class="reading">Soil: <b>%soil%</b><br><meter min="0" max="4095" value="%soil%"></meter></p>
  <p><a class="switch sw-%growLight%" href="/toggle-grow-light"><span class="track"><span class="knob"></span></span> Grow light <b>%growLight%</b></a></p>
  <p class="status st-%growLight2%"><span class="dot"></span> Grow light: <b>%growLight2Text%</b></p>
</main>
</body>
</html>
)";

// The page, with today's numbers put in where %name% is.
String page() {
  String html = PAGE;
  html.replace("%soil%", String(soil));
  html.replace("%growLight%", ledPinOn ? "on" : "off");
  bool growLight2 = ledPinOn;
  html.replace("%growLight2%", growLight2 ? "on" : "off");
  html.replace("%growLight2Text%", growLight2 ? "Shining" : "Off");
  return html;
}

void showPage() {
  server.send(200, "text/html", page());
}

// ---- 4. What happens when someone uses the page ----
void toggleGrowLight() {
  ledPinOn = !ledPinOn;
  digitalWrite(LED_PIN, ledPinOn ? HIGH : LOW);
  Serial.print("Grow light: ");
  Serial.println(ledPinOn ? "on" : "off");
  showPage();
}

void setup() {
  Serial.begin(115200);
  pinMode(LED_PIN, OUTPUT);
  pinMode(SOIL_PIN, INPUT);
  WiFi.softAP(WIFI_NAME, WIFI_PASSWORD);
  server.on("/", showPage);
  server.on("/toggle-grow-light", toggleGrowLight);
  server.begin();
  Serial.print("Open http://");
  Serial.println(WiFi.softAPIP());
}

void loop() {
  server.handleClient();
  soil = analogRead(SOIL_PIN);
}
