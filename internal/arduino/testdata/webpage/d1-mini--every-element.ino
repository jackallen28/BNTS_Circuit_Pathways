// Every element: a web page made with ArduinoPath's Web Page Designer.
// Your board joins the WiFi called "SchoolWiFi". Open the address it prints in the Serial Monitor.

#define LED_PIN D5
#define RGB_RED D5
#define RGB_GREEN D6
#define RGB_BLUE D7
#define BUZZER_PIN D8
#define POT_PIN A0
#define BUTTON_PIN D3
#define PIR_PIN D7

#include <ESP8266WiFi.h>
#include <ESP8266WebServer.h>

// ---- 1. WiFi ----
const char* WIFI_NAME = "SchoolWiFi";
const char* WIFI_PASSWORD = "circuit123";  // at least 8 characters

ESP8266WebServer server(80);

// ---- 2. What the page remembers and shows (change readings in loop) ----
bool ledPinOn = false;  // is LED_PIN on?
int brightness = 50;
String lampColour = "#19c1ca";
int knob = 0;
int pitch = 0;
int number = 0;
int mine2 = 0;

// ---- 3. The page ----
const char PAGE[] = R"(<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="5">
<title>Every element</title>
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
  <h1>Every element</h1>
  <h2>A heading</h2>
  <p>Some words about my project.</p>
  <p><a class="btn" href="/press-me">Press me</a></p>
  <p><a class="switch sw-%light%" href="/toggle-light"><span class="track"><span class="knob"></span></span> Light <b>%light%</b></a></p>
  <form action="/brightness">
    <label>Brightness <b>%brightness%</b><br><input type="range" name="value" min="0" max="100" value="%brightness%"></label>
    <button class="btn">Set</button>
  </form>
  <form action="/set-lamp-colour">
    <label>Lamp colour<br><input type="color" name="value" value="%lampColour%"></label>
    <button class="btn">Set</button>
  </form>
  <p class="reading">Knob: <b>%knob%</b><br><meter min="0" max="1023" value="%knob%"></meter></p>
  <p class="status st-%light2%"><span class="dot"></span> Light: <b>%light2Text%</b></p>
  <p><a class="btn" href="/on">On</a></p>
  <p><a class="btn" href="/off">Off</a></p>
  <p><a class="btn" href="/beep">Beep</a></p>
  <p><a class="btn" href="/mine">Mine</a></p>
  <form action="/pitch">
    <label>Pitch <b>%pitch%</b><br><input type="range" name="value" min="0" max="2000" value="%pitch%"></label>
    <button class="btn">Set</button>
  </form>
  <form action="/number">
    <label>Number <b>%number%</b><br><input type="range" name="value" min="0" max="10" value="%number%"></label>
    <button class="btn">Set</button>
  </form>
  <p class="reading">Mine: <b>%mine2%</b></p>
  <p class="status st-%doorbell%"><span class="dot"></span> Doorbell: <b>%doorbellText%</b></p>
  <p class="status st-%motion%"><span class="dot"></span> Motion: <b>%motionText%</b></p>
</main>
</body>
</html>
)";

// The page, with today's numbers put in where %name% is.
String page() {
  String html = PAGE;
  html.replace("%light%", ledPinOn ? "on" : "off");
  html.replace("%brightness%", String(brightness));
  html.replace("%lampColour%", lampColour);
  html.replace("%knob%", String(knob));
  bool light2 = ledPinOn;
  html.replace("%light2%", light2 ? "on" : "off");
  html.replace("%light2Text%", light2 ? "On" : "Off");
  html.replace("%pitch%", String(pitch));
  html.replace("%number%", String(number));
  html.replace("%mine2%", String(mine2));
  bool doorbell = digitalRead(BUTTON_PIN) == LOW;
  html.replace("%doorbell%", doorbell ? "on" : "off");
  html.replace("%doorbellText%", doorbell ? "Yes" : "No");
  bool motion = digitalRead(PIR_PIN) == HIGH;
  html.replace("%motion%", motion ? "on" : "off");
  html.replace("%motionText%", motion ? "Yes" : "No");
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
void pressMe() {
  ledPinOn = !ledPinOn;
  digitalWrite(LED_PIN, ledPinOn ? HIGH : LOW);
  Serial.println("Press me was pressed");
  showPage();
}

void toggleLight() {
  ledPinOn = !ledPinOn;
  digitalWrite(LED_PIN, ledPinOn ? HIGH : LOW);
  Serial.print("Light: ");
  Serial.println(ledPinOn ? "on" : "off");
  showPage();
}

void setBrightness() {
  brightness = server.arg("value").toInt();
  analogWrite(LED_PIN, map(brightness, 0, 100, 0, 255));
  Serial.print("Brightness: ");
  Serial.println(brightness);
  showPage();
}

void setLampColour() {
  lampColour = server.arg("value");
  analogWrite(RGB_RED, hexValue(lampColour, 1));
  analogWrite(RGB_GREEN, hexValue(lampColour, 3));
  analogWrite(RGB_BLUE, hexValue(lampColour, 5));
  Serial.print("Lamp colour: ");
  Serial.println(lampColour);
  showPage();
}

void on() {
  ledPinOn = true;
  digitalWrite(LED_PIN, ledPinOn ? HIGH : LOW);
  Serial.println("On was pressed");
  showPage();
}

void off() {
  ledPinOn = false;
  digitalWrite(LED_PIN, ledPinOn ? HIGH : LOW);
  Serial.println("Off was pressed");
  showPage();
}

void beep() {
  tone(BUZZER_PIN, 880, 300);  // 880 beats a second, for 300 ms
  Serial.println("Beep was pressed");
  showPage();
}

void mine() {
  // What should "Mine" do? Write it here.
  Serial.println("Mine was pressed");
  showPage();
}

void setPitch() {
  pitch = server.arg("value").toInt();
  if (pitch > 0) tone(BUZZER_PIN, pitch);  // a higher number is a higher note
  else noTone(BUZZER_PIN);
  Serial.print("Pitch: ");
  Serial.println(pitch);
  showPage();
}

void setNumber() {
  number = server.arg("value").toInt();
  // Use number here (it's between 0 and 10).
  Serial.print("Number: ");
  Serial.println(number);
  showPage();
}

void setup() {
  Serial.begin(115200);
  pinMode(LED_PIN, OUTPUT);
  pinMode(RGB_RED, OUTPUT);
  pinMode(RGB_GREEN, OUTPUT);
  pinMode(RGB_BLUE, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(POT_PIN, INPUT);
  pinMode(BUTTON_PIN, INPUT_PULLUP);
  pinMode(PIR_PIN, INPUT);
  WiFi.begin(WIFI_NAME, WIFI_PASSWORD);
  Serial.print("Joining the WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println();
  server.on("/", showPage);
  server.on("/press-me", pressMe);
  server.on("/toggle-light", toggleLight);
  server.on("/brightness", setBrightness);
  server.on("/set-lamp-colour", setLampColour);
  server.on("/on", on);
  server.on("/off", off);
  server.on("/beep", beep);
  server.on("/mine", mine);
  server.on("/pitch", setPitch);
  server.on("/number", setNumber);
  server.begin();
  Serial.print("Open http://");
  Serial.println(WiFi.localIP());
}

void loop() {
  server.handleClient();
  knob = analogRead(POT_PIN);
  // mine2 = ...;  // what should "Mine" show? e.g. analogRead(POT_PIN)
}
