package server

import (
	"errors"
	"strings"
	"unicode"
)

// The same rules as the pages (site/shared/local/validate.js), so a name that works in the browser
// works here.

const (
	maxNames  = 4
	maxName   = 30
	maxSchool = 60
	maxLabel  = 40
)

func squash(s string) string { return strings.Join(strings.Fields(s), " ") }

// cleanName tidies one first name, or returns "" if it isn't one.
func cleanName(s string) string {
	s = squash(s)
	r := []rune(s)
	if len(r) == 0 || len(r) > maxName {
		return ""
	}
	letters := 0
	for _, c := range r {
		switch {
		case unicode.IsLetter(c):
			letters++
		case unicode.Is(unicode.Mn, c) || strings.ContainsRune(" -'’.", c):
		default:
			return ""
		}
	}
	if letters == 0 {
		return ""
	}
	if s == strings.ToLower(s) {
		words := strings.Split(s, " ")
		for i, w := range words {
			if w != "" {
				wr := []rune(w)
				words[i] = strings.ToUpper(string(wr[0])) + string(wr[1:])
			}
		}
		s = strings.Join(words, " ")
	}
	return s
}

func cleanNames(names []string) ([]string, error) {
	if len(names) == 0 || len(names) > maxNames {
		return nil, errors.New("Type 1 to 4 first names.")
	}
	out := []string{}
	for _, n := range names {
		c := cleanName(n)
		if c == "" {
			return nil, errors.New("First names can only have letters, spaces, dashes and apostrophes (up to 30 letters).")
		}
		for _, p := range out {
			if strings.EqualFold(p, c) {
				return nil, errors.New("Each name only needs to be typed once.")
			}
		}
		out = append(out, c)
	}
	return out, nil
}

func cleanSchool(s string) (string, error) {
	s = squash(s)
	r := []rune(s)
	if len(r) == 0 || len(r) > maxSchool {
		return "", errors.New("Type your school's name (up to 60 letters).")
	}
	for _, c := range r {
		if !(unicode.IsLetter(c) || unicode.Is(unicode.Nd, c) || unicode.Is(unicode.Mn, c) || strings.ContainsRune(" -'’.,&()/", c)) {
			return "", errors.New("A school name can only have letters, numbers, spaces and simple punctuation.")
		}
	}
	return s, nil
}

// cleanLabel is a class name: letters, numbers and simple punctuation, up to 40 characters. Not for names.
func cleanLabel(s string) (string, error) {
	s = squash(s)
	if s == "" {
		return "My class", nil
	}
	r := []rune(s)
	ok := len(r) <= maxLabel
	for _, c := range r {
		if !(unicode.IsLetter(c) || unicode.Is(unicode.Nd, c) || strings.ContainsRune(" .,'’&()/#:-", c)) {
			ok = false
		}
	}
	if !ok {
		return "", errors.New("A class name can have letters, numbers and simple punctuation (up to 40). Don't put students' names in it.")
	}
	return s, nil
}
