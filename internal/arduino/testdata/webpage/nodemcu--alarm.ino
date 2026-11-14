// Door Alarm: a web page made with ArduinoPath's Web Page Designer.
// On a phone, join the WiFi called "DoorAlarm", then open the address in the Serial Monitor.

#define LED_PIN D5
#define BUZZER_PIN D8
#define PIR_PIN D7
#define BUTTON_PIN D3

#include <ESP8266WiFi.h>
#include <ESP8266WebServer.h>

// ---- 1. WiFi ----
const char* WIFI_NAME = "DoorAlarm";
const char* WIFI_PASSWORD = "circuit123";  // at least 8 characters

ESP8266WebServer server(80);

// ---- 2. What the page remembers and shows (change readings in loop) ----
bool ledPinOn = false;  // is LED_PIN on?

// ---- 3. The page ----
const char PAGE[] = R"(<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="3">
<title>Door Alarm</title>
<style>
  body { font-family: sans-serif; margin: 0; padding: 16px; background: #f3eef8; color: #2e1d3b; text-align: center; }
  main { max-width: 420px; margin: 0 auto; padding: 16px; border-radius: 16px; background: #ffffff; }
  h1 { color: #704988; }
  .btn { display: inline-block; min-width: 60%; padding: 14px 20px; border: 0; border-radius: 999px; background: #704988; color: #ffffff; font-size: 1.2em; text-decoration: none; }
  input[type=range], meter { width: 90%; }
  input[type=color] { width: 80px; height: 48px; border: 0; }
  .reading b { font-size: 1.6em; color: #704988; }
  .switch { color: inherit; text-decoration: none; font-size: 1.2em; }
  .switch .track { display: inline-block; vertical-align: middle; width: 52px; height: 28px; border-radius: 14px; background: #bbb; position: relative; }
  .switch .knob { position: absolute; top: 3px; left: 3px; width: 22px; height: 22px; border-radius: 50%; background: #fff; }
  .switch.sw-on .track { background: #704988; }
  .switch.sw-on .knob { left: 27px; }
  .switch b { text-transform: uppercase; }
  .status .dot { display: inline-block; width: 16px; height: 16px; border-radius: 50%; background: #bbb; vertical-align: middle; }
  .status.st-on .dot { background: #34c759; box-shadow: 0 0 8px #34c759; }
</style>
</head>
<body>
<main>
  <h1>Door Alarm</h1>
  <p class="status st-%movement%"><span class="dot"></span> Movement: <b>%movementText%</b></p>
  <p class="status st-%doorbell%"><span class="dot"></span> Doorbell: <b>%doorbellText%</b></p>
  <p><a class="btn" href="/sound-the-alarm">Sound the alarm</a></p>
  <p><a class="switch sw-%warningLight%" href="/toggle-warning-light"><span class="track"><span class="knob"></span></span> Warning light <b>%warningLight%</b></a></p>
</main>
</body>
</html>
)";

// The page, with today's numbers put in where %name% is.
String page() {
  String html = PAGE;
  bool movement = digitalRead(PIR_PIN) == HIGH;
  html.replace("%movement%", movement ? "on" : "off");
  html.replace("%movementText%", movement ? "Someone's there!" : "All clear");
  bool doorbell = digitalRead(BUTTON_PIN) == LOW;
  html.replace("%doorbell%", doorbell ? "on" : "off");
  html.replace("%doorbellText%", doorbell ? "Ringing" : "Quiet");
  html.replace("%warningLight%", ledPinOn ? "on" : "off");
  return html;
}

void showPage() {
  server.send(200, "text/html", page());
}

// ---- 4. What happens when someone uses the page ----
void soundTheAlarm() {
  tone(BUZZER_PIN, 880, 300);  // 880 beats a second, for 300 ms
  Serial.println("Sound the alarm was pressed");
  showPage();
}

void toggleWarningLight() {
  ledPinOn = !ledPinOn;
  digitalWrite(LED_PIN, ledPinOn ? HIGH : LOW);
  Serial.print("Warning light: ");
  Serial.println(ledPinOn ? "on" : "off");
  showPage();
}

void setup() {
  Serial.begin(115200);
  pinMode(LED_PIN, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(PIR_PIN, INPUT);
  pinMode(BUTTON_PIN, INPUT_PULLUP);
  WiFi.softAP(WIFI_NAME, WIFI_PASSWORD);
  server.on("/", showPage);
  server.on("/sound-the-alarm", soundTheAlarm);
  server.on("/toggle-warning-light", toggleWarningLight);
  server.begin();
  Serial.print("Open http://");
  Serial.println(WiFi.softAPIP());
}

void loop() {
  server.handleClient();
}
