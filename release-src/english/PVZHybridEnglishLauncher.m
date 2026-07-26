#import <Cocoa/Cocoa.h>
#include <errno.h>
#include <string.h>
#include <unistd.h>

static void ShowError(NSString *message, NSString *details)
{
    [NSApp setActivationPolicy:NSApplicationActivationPolicyAccessory];
    [NSApp activateIgnoringOtherApps:YES];

    NSAlert *alert = [[NSAlert alloc] init];
    alert.alertStyle = NSAlertStyleCritical;
    alert.messageText = message;
    alert.informativeText = details;
    [alert addButtonWithTitle:@"OK"];
    [alert runModal];
}

static BOOL RequirePath(NSString *path, BOOL executable, NSMutableArray<NSString *> *missing)
{
    NSFileManager *fileManager = NSFileManager.defaultManager;
    BOOL isDirectory = NO;
    BOOL exists = [fileManager fileExistsAtPath:path isDirectory:&isDirectory];
    BOOL usable = exists && (!executable || [fileManager isExecutableFileAtPath:path]);
    if (!usable) {
        [missing addObject:path.lastPathComponent];
    }
    return usable;
}

static BOOL RosettaIsAvailable(void)
{
#if defined(__arm64__)
    NSTask *probe = [[NSTask alloc] init];
    probe.executableURL = [NSURL fileURLWithPath:@"/usr/bin/arch"];
    probe.arguments = @[@"-x86_64", @"/usr/bin/true"];
    probe.standardOutput = [NSFileHandle fileHandleWithNullDevice];
    probe.standardError = [NSFileHandle fileHandleWithNullDevice];

    NSError *error = nil;
    if (![probe launchAndReturnError:&error]) {
        return NO;
    }
    [probe waitUntilExit];
    return probe.terminationStatus == 0;
#else
    return YES;
#endif
}

static NSFileHandle *OpenLauncherLog(NSString **logPath)
{
    NSFileManager *fileManager = NSFileManager.defaultManager;
    NSString *directory = [NSHomeDirectory()
        stringByAppendingPathComponent:@"Library/Logs/PVZHybrid025English"];
    [fileManager createDirectoryAtPath:directory
           withIntermediateDirectories:YES
                            attributes:nil
                                 error:nil];

    *logPath = [directory stringByAppendingPathComponent:@"launcher.log"];
    if (![fileManager fileExistsAtPath:*logPath]) {
        [fileManager createFileAtPath:*logPath contents:nil attributes:nil];
    }

    NSFileHandle *handle = [NSFileHandle fileHandleForWritingAtPath:*logPath];
    [handle seekToEndOfFile];
    NSString *header = [NSString stringWithFormat:
        @"\n[%@] Launching Plants vs. Zombies Hybrid v0.25 (English)\n",
        NSDate.date];
    [handle writeData:[header dataUsingEncoding:NSUTF8StringEncoding]];
    return handle;
}

int main(int argc, const char *argv[])
{
    @autoreleasepool {
        (void)argc;
        (void)argv;
        [NSApplication sharedApplication];
        [NSApp setActivationPolicy:NSApplicationActivationPolicyAccessory];

        if (!RosettaIsAvailable()) {
            ShowError(
                @"Rosetta 2 Is Required",
                @"This game contains an Intel runtime. Install the game with the included "
                 "macOS installer so it can check and install Apple's Rosetta 2 component, "
                 "then open the game again."
            );
            return 4;
        }

        NSString *macOS = [NSBundle.mainBundle.bundlePath
            stringByAppendingPathComponent:@"Contents/MacOS"];
        NSString *resources = NSBundle.mainBundle.resourcePath;
        NSString *engine = [macOS stringByAppendingPathComponent:@"PVZHybridGame"];
        NSString *mainPack = [resources stringByAppendingPathComponent:@"PVZHybridGame.pck"];
        NSString *data = [resources
            stringByAppendingPathComponent:@"data_PlantsVsZombies_macos_x86_64"];
        NSString *dotnetRoot = [resources stringByAppendingPathComponent:@"dotnet-x64"];
        NSString *dotnetHost = [dotnetRoot stringByAppendingPathComponent:@"dotnet"];
        NSString *dotnetHostFxr = [dotnetRoot
            stringByAppendingPathComponent:@"host/fxr/9.0.18/libhostfxr.dylib"];
        NSString *assembly = [data stringByAppendingPathComponent:@"PlantsVsZombies.dll"];
        NSString *hostfxr = [data stringByAppendingPathComponent:@"libhostfxr.dylib"];

        NSMutableArray<NSString *> *missing = [NSMutableArray array];
        RequirePath(engine, YES, missing);
        RequirePath(mainPack, NO, missing);
        RequirePath(data, NO, missing);
        RequirePath(dotnetHost, YES, missing);
        RequirePath(dotnetHostFxr, NO, missing);
        RequirePath(assembly, NO, missing);
        RequirePath(hostfxr, NO, missing);

        if (missing.count > 0) {
            NSString *items = [missing componentsJoinedByString:@", "];
            ShowError(
                @"Incomplete Application",
                [NSString stringWithFormat:
                    @"Required components are missing: %@\n\n"
                     "Download and extract the complete English release again.",
                    items]
            );
            return 2;
        }

        NSString *logPath = nil;
        NSFileHandle *logHandle = OpenLauncherLog(&logPath);

        setenv("DOTNET_ROOT", dotnetRoot.fileSystemRepresentation, 1);
        setenv("DOTNET_ROOT_X64", dotnetRoot.fileSystemRepresentation, 1);
        setenv("DOTNET_ROLL_FORWARD", "Major", 1);

        if (chdir(resources.fileSystemRepresentation) != 0) {
            int errorNumber = errno;
            [logHandle closeFile];
            ShowError(
                @"Unable to Open the Game Resources",
                [NSString stringWithFormat:
                    @"%@\n\nLog file: %@",
                    [NSString stringWithUTF8String:strerror(errorNumber)],
                    logPath]
            );
            return 3;
        }

        int logDescriptor = logHandle.fileDescriptor;
        if (dup2(logDescriptor, STDOUT_FILENO) == -1 ||
            dup2(logDescriptor, STDERR_FILENO) == -1) {
            int errorNumber = errno;
            [logHandle closeFile];
            ShowError(
                @"Unable to Open the Launcher Log",
                [NSString stringWithFormat:
                    @"%@\n\nLog file: %@",
                    [NSString stringWithUTF8String:strerror(errorNumber)],
                    logPath]
            );
            return 3;
        }
        [logHandle closeFile];

        const char *arguments[] = {
            "/usr/bin/arch",
            "-x86_64",
            engine.fileSystemRepresentation,
            "--rendering-driver",
            "opengl3",
            "--language",
            "en",
            NULL,
        };
        execv(arguments[0], (char *const *)arguments);

        int errorNumber = errno;
        ShowError(
            @"Unable to Launch the Game",
            [NSString stringWithFormat:
                @"%@\n\nLog file: %@\n\n"
                 "On Apple silicon, install Rosetta 2 and try again.",
                [NSString stringWithUTF8String:strerror(errorNumber)],
                logPath]
        );
        return 3;
    }
}
