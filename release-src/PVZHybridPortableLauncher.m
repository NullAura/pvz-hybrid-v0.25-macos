#import <Cocoa/Cocoa.h>

static void ShowError(NSString *message, NSString *details)
{
    [NSApp setActivationPolicy:NSApplicationActivationPolicyAccessory];
    [NSApp activateIgnoringOtherApps:YES];

    NSAlert *alert = [[NSAlert alloc] init];
    alert.alertStyle = NSAlertStyleCritical;
    alert.messageText = message;
    alert.informativeText = details;
    [alert addButtonWithTitle:@"确定 / OK"];
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

static NSFileHandle *OpenLauncherLog(NSString **logPath)
{
    NSFileManager *fileManager = NSFileManager.defaultManager;
    NSString *directory = [NSHomeDirectory() stringByAppendingPathComponent:@"Library/Logs/PVZHybrid025"];
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
    NSString *header = [NSString stringWithFormat:@"\n[%@] Launching PVZ Hybrid v0.25\n", NSDate.date];
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

        NSString *macOS = [NSBundle.mainBundle.bundlePath stringByAppendingPathComponent:@"Contents/MacOS"];
        NSString *resources = NSBundle.mainBundle.resourcePath;
        NSString *engine = [macOS stringByAppendingPathComponent:@"PVZHybridGame"];
        NSString *mainPack = [resources stringByAppendingPathComponent:@"PVZHybridGame.pck"];
        NSString *data = [resources stringByAppendingPathComponent:@"data_PlantsVsZombies_macos_x86_64"];
        NSString *assembly = [data stringByAppendingPathComponent:@"PlantsVsZombies.dll"];
        NSString *hostfxr = [data stringByAppendingPathComponent:@"libhostfxr.dylib"];

        NSMutableArray<NSString *> *missing = [NSMutableArray array];
        RequirePath(engine, YES, missing);
        RequirePath(mainPack, NO, missing);
        RequirePath(data, NO, missing);
        RequirePath(assembly, NO, missing);
        RequirePath(hostfxr, NO, missing);

        if (missing.count > 0) {
            ShowError(
                @"游戏文件不完整 / Incomplete game package",
                [NSString stringWithFormat:
                    @"缺少以下组件：%@\n\n请重新解压完整的发行包。\n"
                     "Missing components: %@\n\nPlease extract the complete release again.",
                    [missing componentsJoinedByString:@", "],
                    [missing componentsJoinedByString:@", "]]
            );
            return 2;
        }

        NSString *logPath = nil;
        NSFileHandle *logHandle = OpenLauncherLog(&logPath);

        NSTask *task = [[NSTask alloc] init];
        task.executableURL = [NSURL fileURLWithPath:@"/usr/bin/arch"];
        task.arguments = @[
            @"-x86_64",
            engine,
            @"--rendering-driver", @"opengl3"
        ];
        task.currentDirectoryURL = [NSURL fileURLWithPath:resources isDirectory:YES];
        task.standardOutput = logHandle;
        task.standardError = logHandle;

        NSError *launchError = nil;
        if (![task launchAndReturnError:&launchError]) {
            [logHandle closeFile];
            ShowError(
                @"游戏启动失败 / Launch failed",
                [NSString stringWithFormat:
                    @"%@\n\n日志：%@\n\nApple 芯片 Mac 需要先安装 Rosetta 2。\n"
                     "Log: %@\n\nApple Silicon Macs require Rosetta 2.",
                    launchError.localizedDescription, logPath, logPath]
            );
            return 3;
        }

        [task waitUntilExit];
        int status = task.terminationStatus;
        [logHandle closeFile];

        if (status != 0) {
            ShowError(
                @"游戏异常退出 / Game exited unexpectedly",
                [NSString stringWithFormat:
                    @"退出代码：%d\n日志：%@\n\n"
                     "如果使用 Apple 芯片 Mac，请确认已安装 Rosetta 2。\n"
                     "Exit code: %d\nLog: %@\n\n"
                     "On Apple Silicon, make sure Rosetta 2 is installed.",
                    status, logPath, status, logPath]
            );
        }
        return status;
    }
}
