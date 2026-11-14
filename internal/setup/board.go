package setup

import "fmt"

// BoardSketch is what an ESP board is flashed with when the teacher sets it up: it makes the board's own WiFi
// (so the teacher can check it with a phone), shows a page with its label, and says who it is on the Serial
// Monitor. Everything in it comes from the server's own safe alphabets.
func BoardSketch(label, ssid, password string) string {
	return fmt.Sprintf(`// Circuit Pathways: board set-up for %[1]s. A student claims this board with its code, then their
// WiFi projects use this board's own WiFi name and password.
#if defined(ESP8266)
#include <ESP8266WiFi.h>
#include <ESP8266WebServer.h>
ESP8266WebServer server(80);
#else
#include <WiFi.h>
#include <WebServer.h>
WebServer server(80);
#endif

const char* BOARD_LABEL = "%[1]s";
const char* WIFI_NAME = "%[2]s";
const char* WIFI_PASSWORD = "%[3]s";
unsigned long last = 0;

void homePage() {
  String page = "<!DOCTYPE html><html><head><meta name=\"viewport\" content=\"width=device-width\"></head>";
  page += "<body style=\"font-family: sans-serif; text-align: center\"><h1>";
  page += BOARD_LABEL;
  page += "</h1><p>This Circuit Pathways board is set up and ready.</p></body></html>";
  server.send(200, "text/html", page);
}

void setup() {
  Serial.begin(115200);
#ifdef LED_BUILTIN
  pinMode(LED_BUILTIN, OUTPUT);
#endif
  WiFi.softAP(WIFI_NAME, WIFI_PASSWORD);
  server.on("/", homePage);
  server.begin();
}

void loop() {
  server.handleClient();
  if (millis() - last > 2000) {
    last = millis();
    Serial.print("Circuit Pathways board ");
    Serial.print(BOARD_LABEL);
    Serial.print(": WiFi ");
    Serial.print(WIFI_NAME);
    Serial.print(" at http://");
    Serial.println(WiFi.softAPIP());
#ifdef LED_BUILTIN
    digitalWrite(LED_BUILTIN, !digitalRead(LED_BUILTIN));
#endif
  }
}
`, label, ssid, password)
}
