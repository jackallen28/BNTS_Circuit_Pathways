/* Made from the two apps' own content files (PiPath catalog.toml, ArduinoPath content/). */
window.CP_DATA = {
 "pipath": {
  "tiers": [
   {
    "id": "simple",
    "title": "Simple",
    "tagline": "Python on the screen"
   },
   {
    "id": "moderate",
    "title": "Moderate",
    "tagline": "Bigger programs"
   },
   {
    "id": "computer",
    "title": "Pi & Computer",
    "tagline": "Hardware that talks to the computer"
   },
   {
    "id": "advanced",
    "title": "Advanced",
    "tagline": "Electronics with GPIO"
   },
   {
    "id": "lab",
    "title": "Electronics Lab",
    "tagline": "Extra hardware projects"
   },
   {
    "id": "camera",
    "title": "Camera & AI",
    "tagline": "See and learn"
   }
  ],
  "projects": [
   {
    "id": "s1_hello",
    "tier": "simple",
    "title": "Hello, Pi!",
    "subtitle": "Your first program, and your first bug hunt",
    "gpio": false,
    "camera": false,
    "minutes": 15
   },
   {
    "id": "s2_pibot",
    "tier": "simple",
    "title": "Meet PiBot",
    "subtitle": "A chatbot that asks questions and remembers answers",
    "gpio": false,
    "camera": false,
    "minutes": 20
   },
   {
    "id": "s3_guess",
    "tier": "simple",
    "title": "Guess My Number",
    "subtitle": "A game with a secret, some clues and a loop",
    "gpio": false,
    "camera": false,
    "minutes": 30
   },
   {
    "id": "m1_quiz",
    "tier": "moderate",
    "title": "Quiz Master",
    "subtitle": "A trivia game with lists, a scoring function and shuffled questions",
    "gpio": false,
    "camera": false,
    "minutes": 40
   },
   {
    "id": "m2_turtle",
    "tier": "moderate",
    "title": "Turtle Art Studio",
    "subtitle": "Draw shapes and spinning rainbow patterns with code",
    "gpio": false,
    "camera": false,
    "minutes": 40
   },
   {
    "id": "m3_tuckshop",
    "tier": "moderate",
    "title": "Tuckshop Till",
    "subtitle": "A till that totals orders, prints receipts and logs the day's sales",
    "gpio": false,
    "camera": false,
    "minutes": 50
   },
   {
    "id": "p1_pihealth",
    "tier": "computer",
    "title": "Pi Health Lights",
    "subtitle": "Three LEDs glow with the Pi's temperature, CPU load and memory",
    "gpio": true,
    "camera": false,
    "minutes": 45
   },
   {
    "id": "p2_binaryclock",
    "tier": "computer",
    "title": "Binary Clock",
    "subtitle": "The Pi's clock ticking in binary on six LEDs",
    "gpio": true,
    "camera": false,
    "minutes": 45
   },
   {
    "id": "p3_dicedj",
    "tier": "computer",
    "title": "Dice DJ",
    "subtitle": "Roll an LED dice and the computer plays a sound, song or video",
    "gpio": true,
    "camera": false,
    "minutes": 45
   },
   {
    "id": "p4_doorbell",
    "tier": "computer",
    "title": "Doorbell Cam",
    "subtitle": "A visitor comes close: ring, snap their photo and show it on the screen",
    "gpio": true,
    "camera": true,
    "minutes": 55
   },
   {
    "id": "p5_focustimer",
    "tier": "computer",
    "title": "Focus Timer",
    "subtitle": "A study timer: a shrinking bar of lights, a beep and a break message",
    "gpio": true,
    "camera": false,
    "minutes": 45
   },
   {
    "id": "p6_controlpad",
    "tier": "computer",
    "title": "Control Pad",
    "subtitle": "Three buttons that take a screenshot, change the volume and open your favourite website",
    "gpio": true,
    "camera": false,
    "minutes": 40
   },
   {
    "id": "a1_traffic",
    "tier": "advanced",
    "title": "Traffic Lights",
    "subtitle": "Three LEDs and a pedestrian button",
    "gpio": true,
    "camera": false,
    "minutes": 55
   },
   {
    "id": "a2_reaction",
    "tier": "advanced",
    "title": "Reaction Timer",
    "subtitle": "Who is fastest? A two-player button game",
    "gpio": true,
    "camera": false,
    "minutes": 60
   },
   {
    "id": "a3_alarm",
    "tier": "advanced",
    "title": "Motion Alarm & Logger",
    "subtitle": "An ultrasonic alarm that arms, beeps and keeps a log",
    "gpio": true,
    "camera": false,
    "minutes": 65
   },
   {
    "id": "e1_lightswitch",
    "tier": "lab",
    "title": "Light Switch Lab",
    "subtitle": "Buttons that switch, toggle and dim an LED",
    "gpio": true,
    "camera": false,
    "minutes": 35
   },
   {
    "id": "e2_moodlamp",
    "tier": "lab",
    "title": "RGB Mood Lamp",
    "subtitle": "Mix any colour with one LED, then build a colour-changing lamp",
    "gpio": true,
    "camera": false,
    "minutes": 45
   },
   {
    "id": "e3_simon",
    "tier": "lab",
    "title": "Simon Says",
    "subtitle": "A memory game: repeat the light pattern as it gets longer",
    "gpio": true,
    "camera": false,
    "minutes": 60
   },
   {
    "id": "e4_dice",
    "tier": "lab",
    "title": "Bar Graph & Digital Dice",
    "subtitle": "Six LEDs as a level meter, a counter and a dice you can shake",
    "gpio": true,
    "camera": false,
    "minutes": 50
   },
   {
    "id": "e5_parking",
    "tier": "lab",
    "title": "Parking Sensor",
    "subtitle": "A car reversing beeper: lights and beeps that speed up as you get closer",
    "gpio": true,
    "camera": false,
    "minutes": 50
   },
   {
    "id": "e6_whackamole",
    "tier": "lab",
    "title": "Whack-a-Mole",
    "subtitle": "An arcade game: whack the mole that lights up before it hides",
    "gpio": true,
    "camera": false,
    "minutes": 55
   },
   {
    "id": "e7_morse",
    "tier": "lab",
    "title": "Morse Code Messenger",
    "subtitle": "Send secret messages with light and sound, and tap them in with a key",
    "gpio": true,
    "camera": false,
    "minutes": 55
   },
   {
    "id": "c1_photobooth",
    "tier": "camera",
    "title": "Photo Booth",
    "subtitle": "Press the button, watch the 3-2-1 countdown, smile!",
    "gpio": true,
    "camera": true,
    "minutes": 45
   },
   {
    "id": "c2_teachable",
    "tier": "camera",
    "title": "Teachable Machine",
    "subtitle": "Teach the Pi to tell two things apart: real machine learning",
    "gpio": true,
    "camera": true,
    "minutes": 65
   }
  ]
 },
 "arduinopath": {
  "tiers": [
   {
    "id": "getting-started",
    "title": "Getting Started",
    "tagline": "Your first circuits: LEDs, buttons and the Serial Monitor."
   },
   {
    "id": "sensors-sound",
    "title": "Sensors & Sound",
    "tagline": "Read the world with sensors and make some noise."
   },
   {
    "id": "displays-lights",
    "title": "Displays & Lights",
    "tagline": "Screens, colour lights and number displays."
   },
   {
    "id": "games",
    "title": "Games",
    "tagline": "Build games to play with your friends."
   },
   {
    "id": "wifi-iot",
    "title": "WiFi & IoT",
    "tagline": "Connect an ESP board to WiFi and control it from your phone."
   },
   {
    "id": "challenge",
    "title": "Challenge",
    "tagline": "Bigger builds with lots of parts working together."
   }
  ],
  "projects": [
   {
    "id": "blink-traffic-lights",
    "tier": "getting-started",
    "title": "Blink & Traffic Lights",
    "intro": "Make an LED blink, then add two more and run them like real traffic lights.",
    "order": 1,
    "boards": [
     "all"
    ],
    "minutes": 45
   },
   {
    "id": "button-night-light",
    "tier": "getting-started",
    "title": "Button Night Light",
    "intro": "Press a button to turn a light on and off. Then make it remember what it was doing.",
    "order": 2,
    "boards": [
     "all"
    ],
    "minutes": 45
   },
   {
    "id": "serial-chatbot",
    "tier": "getting-started",
    "title": "Serial Chatbot",
    "intro": "No wiring needed! Write a chatbot that talks to you in the Serial Monitor.",
    "order": 3,
    "boards": [
     "all"
    ],
    "minutes": 45
   },
   {
    "id": "smart-bin",
    "tier": "getting-started",
    "title": "Smart Bin",
    "intro": "Build a bin that opens its lid by itself when a hand comes close: no touching!",
    "order": 4,
    "boards": [
     "all"
    ],
    "minutes": 60
   },
   {
    "id": "light-theremin",
    "tier": "sensors-sound",
    "title": "Light Theremin",
    "intro": "Wave your hand over a light sensor to play music, like a real theremin.",
    "order": 4,
    "boards": [
     "all"
    ],
    "minutes": 60
   },
   {
    "id": "servo-dial",
    "tier": "sensors-sound",
    "title": "Servo Dial",
    "intro": "Turn a knob and a servo motor follows it, like a dial on a dashboard.",
    "order": 5,
    "boards": [
     "all"
    ],
    "minutes": 45
   },
   {
    "id": "parking-sensor",
    "tier": "sensors-sound",
    "title": "Parking Sensor",
    "intro": "Measure distance with sound waves, then beep faster and light up as something gets closer.",
    "order": 6,
    "boards": [
     "all"
    ],
    "minutes": 90
   },
   {
    "id": "motion-alarm",
    "tier": "sensors-sound",
    "title": "Motion Alarm",
    "intro": "Catch anyone sneaking past with a motion sensor, a flashing light and an alarm.",
    "order": 7,
    "boards": [
     "all"
    ],
    "minutes": 60
   },
   {
    "id": "weather-station",
    "tier": "displays-lights",
    "title": "Weather Station",
    "intro": "Read the temperature and humidity and show them on a little OLED screen.",
    "order": 8,
    "boards": [
     "all"
    ],
    "minutes": 90
   },
   {
    "id": "neopixel-mood-lamp",
    "tier": "displays-lights",
    "title": "NeoPixel Mood Lamp",
    "intro": "Build a glowing lamp. Turn the knob to change the colour and press the button for light shows.",
    "order": 9,
    "boards": [
     "all"
    ],
    "minutes": 75
   },
   {
    "id": "digital-dice",
    "tier": "displays-lights",
    "title": "Digital Dice",
    "intro": "Press a button to roll the dice and show the number on a 4-digit display.",
    "order": 10,
    "boards": [
     "all"
    ],
    "minutes": 60
   },
   {
    "id": "plant-buddy",
    "tier": "displays-lights",
    "title": "Plant Buddy",
    "intro": "Check if a plant needs water. Show a happy or thirsty face on the screen.",
    "order": 11,
    "boards": [
     "all"
    ],
    "minutes": 75
   },
   {
    "id": "reaction-race",
    "tier": "games",
    "title": "Reaction Race",
    "intro": "A game for 2 players. Wait for the light, then race to press your button first!",
    "order": 12,
    "boards": [
     "all"
    ],
    "minutes": 75
   },
   {
    "id": "simon-says",
    "tier": "games",
    "title": "Simon Says",
    "intro": "Watch the pattern of lights and sounds, then copy it. It gets longer every round.",
    "order": 13,
    "boards": [
     "all"
    ],
    "minutes": 120
   },
   {
    "id": "joystick-snake",
    "tier": "games",
    "title": "Joystick Snake",
    "intro": "Steer a snake around an 8×8 LED matrix with a joystick. Eat the dots to grow!",
    "order": 14,
    "boards": [
     "avr",
     "esp32"
    ],
    "minutes": 150
   },
   {
    "id": "phone-led",
    "tier": "wifi-iot",
    "title": "Phone-controlled LED",
    "intro": "Make your own web page that turns an LED on and off from your phone.",
    "order": 17,
    "boards": [
     "esp"
    ],
    "minutes": 60
   },
   {
    "id": "weather-web-page",
    "tier": "wifi-iot",
    "title": "Weather Web Page",
    "intro": "Show the temperature and humidity on a web page anyone in the room can open.",
    "order": 18,
    "boards": [
     "esp"
    ],
    "minutes": 90
   },
   {
    "id": "neopixel-remote",
    "tier": "wifi-iot",
    "title": "NeoPixel Remote",
    "intro": "Slide sliders on a web page to change the colours of a NeoPixel strip.",
    "order": 19,
    "boards": [
     "esp"
    ],
    "minutes": 90
   },
   {
    "id": "internet-clock",
    "tier": "wifi-iot",
    "title": "Internet Clock",
    "intro": "Get the exact time from the internet and show it on an OLED screen.",
    "order": 20,
    "boards": [
     "esp"
    ],
    "minutes": 60
   },
   {
    "id": "esp-now-messenger",
    "tier": "wifi-iot",
    "title": "ESP-NOW Messenger",
    "intro": "Send messages between two boards with no router. Press a button and your friend's board buzzes.",
    "order": 21,
    "boards": [
     "esp32"
    ],
    "minutes": 120
   },
   {
    "id": "wifi-scanner-radar",
    "tier": "wifi-iot",
    "title": "WiFi Scanner Radar",
    "intro": "Find the WiFi networks around you and show how strong each one is.",
    "order": 22,
    "boards": [
     "esp"
    ],
    "minutes": 60
   },
   {
    "id": "keypad-safe",
    "tier": "challenge",
    "title": "Keypad Safe",
    "intro": "Type the secret code on a keypad to unlock a safe. A servo opens the lock.",
    "order": 15,
    "boards": [
     "uno",
     "mega"
    ],
    "minutes": 120
   },
   {
    "id": "rfid-door",
    "tier": "challenge",
    "title": "RFID Door",
    "intro": "Tap the right card to open the door. The wrong card gets a red light.",
    "order": 16,
    "boards": [
     "all"
    ],
    "minutes": 120
   }
  ],
  "parts": {
   "hc-sr04": {
    "name": "ultrasonic distance sensor (HC-SR04)",
    "what": "An ultrasonic sensor measures distance. It squeaks too high for us to hear and times the echo, like a bat.",
    "legs": "The pins are labelled: VCC (5V), Trig, Echo and Gnd. On a 3.3V board, Echo needs two resistors to make it safe.",
    "did_you_know": "Sound travels about 343 metres every second, so an echo from 1 metre away comes back in under a hundredth of a second."
   },
   "servo": {
    "name": "servo motor",
    "what": "A servo is a motor that turns to the angle you choose, from 0° to 180°, and holds there.",
    "legs": "It has three wires: brown (or black) is GND, red is power (5V) and orange (or yellow) is the signal.",
    "did_you_know": "Servos steer remote-control cars and move the arms of robots."
   },
   "led": {
    "name": "LED",
    "what": "An LED is a tiny light. It glows when electricity flows through it the right way.",
    "legs": "The long leg is + (the anode). The short leg is − (the cathode), on the side where the rim is flat.",
    "did_you_know": "LED stands for light-emitting diode. LEDs use far less power than old light globes and can last for 50,000 hours."
   },
   "resistor-220": {
    "name": "220Ω resistor",
    "what": "A resistor slows down the electricity. A 220Ω resistor keeps an LED from getting too much and burning out.",
    "legs": "It works either way round. Read its colour bands: red, red, brown means 220Ω.",
    "did_you_know": "The coloured bands are a code. Red is 2 and brown means 'add one zero', so red-red-brown is 22 then 0: 220."
   }
  },
  "boards": {
   "d1-mini": {
    "name": "Wemos / LOLIN D1 mini (ESP8266)",
    "volts": 3.3,
    "wifi": true,
    "order": 5,
    "pins": {
     "TRIG_PIN": "D1",
     "ECHO_PIN": "D2",
     "SERVO_PIN": "D6",
     "LED_PIN": "D5"
    }
   },
   "nodemcu": {
    "name": "NodeMCU 1.0 (ESP8266)",
    "volts": 3.3,
    "wifi": true,
    "order": 4,
    "pins": {
     "TRIG_PIN": "D1",
     "ECHO_PIN": "D2",
     "SERVO_PIN": "D6",
     "LED_PIN": "D5"
    }
   },
   "mega": {
    "name": "Arduino Mega 2560",
    "volts": 5,
    "wifi": false,
    "order": 3,
    "pins": {
     "TRIG_PIN": "6",
     "ECHO_PIN": "7",
     "SERVO_PIN": "9",
     "LED_PIN": "13"
    }
   },
   "uno": {
    "name": "Arduino Uno R3",
    "volts": 5,
    "wifi": false,
    "order": 1,
    "pins": {
     "TRIG_PIN": "6",
     "ECHO_PIN": "7",
     "SERVO_PIN": "9",
     "LED_PIN": "13"
    }
   },
   "nano": {
    "name": "Arduino Nano",
    "volts": 5,
    "wifi": false,
    "order": 2,
    "pins": {
     "TRIG_PIN": "6",
     "ECHO_PIN": "7",
     "SERVO_PIN": "9",
     "LED_PIN": "13"
    }
   },
   "esp32": {
    "name": "ESP32 DevKit V1 (ESP32-WROOM-32)",
    "volts": 3.3,
    "wifi": true,
    "order": 6,
    "pins": {
     "TRIG_PIN": "16",
     "ECHO_PIN": "17",
     "SERVO_PIN": "32",
     "LED_PIN": "25"
    }
   },
   "esp32-c3": {
    "name": "ESP32-C3 SuperMini",
    "volts": 3.3,
    "wifi": true,
    "order": 7,
    "pins": {
     "TRIG_PIN": "20",
     "ECHO_PIN": "21",
     "SERVO_PIN": "7",
     "LED_PIN": "10"
    }
   }
  }
 }
};
