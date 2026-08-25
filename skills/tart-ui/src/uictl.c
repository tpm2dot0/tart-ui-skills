// uictl — post synthetic mouse/keyboard events and report display geometry.
// Built on the host with clang and copied into the guest, which therefore needs
// no compiler and no package manager. TCC attributes these events to the SSH
// session's responsible process, which provision.sh grants
// Accessibility/PostEvent.
//
//   clang -O2 -o uictl uictl.c -framework ApplicationServices -framework CoreFoundation
#include <ApplicationServices/ApplicationServices.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static const struct { const char *name; CGKeyCode code; } KEYS[] = {
  {"a",0},{"s",1},{"d",2},{"f",3},{"h",4},{"g",5},{"z",6},{"x",7},{"c",8},{"v",9},
  {"b",11},{"q",12},{"w",13},{"e",14},{"r",15},{"y",16},{"t",17},
  {"1",18},{"2",19},{"3",20},{"4",21},{"6",22},{"5",23},{"equal",24},{"9",25},
  {"7",26},{"minus",27},{"8",28},{"0",29},{"rightbracket",30},{"o",31},{"u",32},
  {"leftbracket",33},{"i",34},{"p",35},{"return",36},{"enter",36},{"l",37},{"j",38},
  {"quote",39},{"k",40},{"semicolon",41},{"backslash",42},{"comma",43},{"slash",44},
  {"n",45},{"m",46},{"period",47},{"tab",48},{"space",49},{"grave",50},
  {"delete",51},{"backspace",51},{"escape",53},{"esc",53},
  {"f5",96},{"f6",97},{"f7",98},{"f3",99},{"f8",100},{"f9",101},{"f11",103},
  {"f10",109},{"f12",111},{"help",114},{"home",115},{"pageup",116},
  {"forwarddelete",117},{"f4",118},{"end",119},{"f2",120},{"pagedown",121},{"f1",122},
  {"left",123},{"right",124},{"down",125},{"up",126},
};

static int key_for(const char *n, CGKeyCode *out) {
  for (size_t i = 0; i < sizeof(KEYS)/sizeof(KEYS[0]); i++)
    if (strcasecmp(KEYS[i].name, n) == 0) { *out = KEYS[i].code; return 1; }
  return 0;
}

static CGEventFlags mod_for(const char *n) {
  if (!strcasecmp(n,"cmd")||!strcasecmp(n,"command")) return kCGEventFlagMaskCommand;
  if (!strcasecmp(n,"shift"))                          return kCGEventFlagMaskShift;
  if (!strcasecmp(n,"alt")||!strcasecmp(n,"option")||!strcasecmp(n,"opt"))
                                                       return kCGEventFlagMaskAlternate;
  if (!strcasecmp(n,"ctrl")||!strcasecmp(n,"control"))  return kCGEventFlagMaskControl;
  if (!strcasecmp(n,"fn"))                              return kCGEventFlagMaskSecondaryFn;
  return 0;
}

static void post(CGEventRef e) {
  if (!e) return;
  CGEventPost(kCGHIDEventTap, e);
  CFRelease(e);
  usleep(12000); // give the target app a frame to react
}

static void mouse(CGEventType t, CGPoint p, CGMouseButton b, int clicks) {
  CGEventRef e = CGEventCreateMouseEvent(NULL, t, p, b);
  if (clicks > 1) CGEventSetIntegerValueField(e, kCGMouseEventClickState, clicks);
  post(e);
}

static void tap_key(CGKeyCode code, CGEventFlags flags) {
  CGEventRef d = CGEventCreateKeyboardEvent(NULL, code, true);
  CGEventSetFlags(d, flags); post(d);
  CGEventRef u = CGEventCreateKeyboardEvent(NULL, code, false);
  CGEventSetFlags(u, flags); post(u);
}

int main(int argc, char **argv) {
  if (argc < 2) {
    fprintf(stderr,
      "uictl size | move X Y | click X Y [left|right] [count]\n"
      "      drag X1 Y1 X2 Y2 | scroll DY [DX] | key NAME [mod...] | type TEXT\n");
    return 2;
  }
  const char *cmd = argv[1];

  if (!strcmp(cmd, "size")) {
    CGDirectDisplayID d = CGMainDisplayID();
    printf("%zux%zu\n", CGDisplayPixelsWide(d), CGDisplayPixelsHigh(d));
    return 0;
  }
  if (!strcmp(cmd, "move") && argc >= 4) {
    mouse(kCGEventMouseMoved, CGPointMake(atof(argv[2]), atof(argv[3])), 0, 1);
    return 0;
  }
  if (!strcmp(cmd, "click") && argc >= 4) {
    CGPoint p = CGPointMake(atof(argv[2]), atof(argv[3]));
    int right = (argc >= 5 && !strcasecmp(argv[4], "right"));
    int n = (argc >= 6) ? atoi(argv[5]) : 1;
    CGMouseButton b = right ? kCGMouseButtonRight : kCGMouseButtonLeft;
    mouse(kCGEventMouseMoved, p, b, 1);
    for (int i = 1; i <= n; i++) {
      mouse(right ? kCGEventRightMouseDown : kCGEventLeftMouseDown, p, b, i);
      mouse(right ? kCGEventRightMouseUp   : kCGEventLeftMouseUp,   p, b, i);
    }
    return 0;
  }
  if (!strcmp(cmd, "drag") && argc >= 6) {
    CGPoint a = CGPointMake(atof(argv[2]), atof(argv[3]));
    CGPoint b = CGPointMake(atof(argv[4]), atof(argv[5]));
    mouse(kCGEventMouseMoved, a, kCGMouseButtonLeft, 1);
    mouse(kCGEventLeftMouseDown, a, kCGMouseButtonLeft, 1);
    // Interpolate: many views ignore a single jump from press to release.
    for (int i = 1; i <= 10; i++) {
      CGPoint m = CGPointMake(a.x + (b.x-a.x)*i/10.0, a.y + (b.y-a.y)*i/10.0);
      mouse(kCGEventLeftMouseDragged, m, kCGMouseButtonLeft, 1);
    }
    mouse(kCGEventLeftMouseUp, b, kCGMouseButtonLeft, 1);
    return 0;
  }
  if (!strcmp(cmd, "scroll") && argc >= 3) {
    int32_t dy = atoi(argv[2]), dx = (argc >= 4) ? atoi(argv[3]) : 0;
    post(CGEventCreateScrollWheelEvent(NULL, kCGScrollEventUnitLine, 2, dy, dx));
    return 0;
  }
  if (!strcmp(cmd, "key") && argc >= 3) {
    CGKeyCode code;
    if (!key_for(argv[2], &code)) { fprintf(stderr, "unknown key: %s\n", argv[2]); return 1; }
    CGEventFlags f = 0;
    for (int i = 3; i < argc; i++) f |= mod_for(argv[i]);
    tap_key(code, f);
    return 0;
  }
  if (!strcmp(cmd, "type") && argc >= 3) {
    // Join the remaining argv so the caller need not quote perfectly.
    char buf[8192]; buf[0] = 0;
    for (int i = 2; i < argc; i++) {
      if (i > 2) strlcat(buf, " ", sizeof buf);
      strlcat(buf, argv[i], sizeof buf);
    }
    CFStringRef s = CFStringCreateWithCString(NULL, buf, kCFStringEncodingUTF8);
    if (!s) { fprintf(stderr, "bad utf-8\n"); return 1; }
    CFIndex n = CFStringGetLength(s);
    UniChar *u = malloc(sizeof(UniChar) * (n ? n : 1));
    CFStringGetCharacters(s, CFRangeMake(0, n), u);
    // One event per character: a single event carrying a long string drops
    // input in several apps.
    for (CFIndex i = 0; i < n; i++) {
      CGEventRef d = CGEventCreateKeyboardEvent(NULL, 0, true);
      CGEventKeyboardSetUnicodeString(d, 1, &u[i]); post(d);
      CGEventRef up = CGEventCreateKeyboardEvent(NULL, 0, false);
      CGEventKeyboardSetUnicodeString(up, 1, &u[i]); post(up);
    }
    free(u); CFRelease(s);
    return 0;
  }
  fprintf(stderr, "bad usage\n");
  return 2;
}
