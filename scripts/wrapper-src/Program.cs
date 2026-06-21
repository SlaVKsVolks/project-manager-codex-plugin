using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Threading;

static class Program
{
    private const uint TH32CS_SNAPPROCESS = 0x00000002;
    private const int MaxExeNameChars = 260;

    private static readonly IntPtr InvalidHandleValue = new(-1);
    private static readonly object LogLock = new();
    private static readonly TimeSpan InitialInputTimeout = TimeSpan.FromSeconds(ReadPositiveIntEnv("PROJECT_MANAGER_WRAPPER_INITIAL_INPUT_TIMEOUT_SECONDS", 10));
    private static readonly bool DuplicateMonitorEnabled = ReadBoolEnv("PROJECT_MANAGER_WRAPPER_DUPLICATE_MONITOR_ENABLED", true);
    private static readonly TimeSpan DuplicateIdleThreshold = TimeSpan.FromSeconds(ReadPositiveIntEnv("PROJECT_MANAGER_WRAPPER_DUPLICATE_IDLE_SECONDS", 120));
    private static readonly TimeSpan DuplicateMonitorPollInterval = TimeSpan.FromSeconds(ReadPositiveIntEnv("PROJECT_MANAGER_WRAPPER_DUPLICATE_POLL_SECONDS", 15));
    private static readonly int SafeSiblingLimit = ReadPositiveIntEnv("PROJECT_MANAGER_WRAPPER_SIBLING_LIMIT", 3);
    private static readonly TimeSpan ServerStartDedupWindow = TimeSpan.FromSeconds(ReadPositiveIntEnv("PROJECT_MANAGER_WRAPPER_SERVER_START_DEDUP_SECONDS", 20));

    public static async Task<int> Main()
    {
        string? logPath = TryResolveWrapperLogPath();
        try
        {
            return await MainImpl(logPath).ConfigureAwait(false);
        }
        catch (Exception ex)
        {
            Log(logPath, $"fatal_exception type={ex.GetType().Name} message={Sanitize(ex.Message)}");
            try
            {
                Console.Error.WriteLine($"project-manager-mcp fatal: {Sanitize(ex.ToString())}");
            }
            catch
            {
            }

            return 1;
        }
    }

    private static async Task<int> MainImpl(string? logPath)
    {
        var scriptDir = AppContext.BaseDirectory.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
        var pluginRoot = Directory.GetParent(scriptDir)?.FullName ?? scriptDir;
        var scriptPath = Path.Combine(scriptDir, "project_manager_mcp_server.py");
        var pythonExe = ResolvePythonExe();
        var parentPid = TryGetParentProcessId();
        var currentPid = Environment.ProcessId;
        var currentExeName = Path.GetFileName(Environment.ProcessPath) ?? "project-manager-mcp.exe";
        var wrapperPath = Environment.ProcessPath ?? Path.Combine(scriptDir, "project-manager-mcp.exe");
        var wrapperHash = TryComputeFileHash(wrapperPath) ?? "unknown";
        var launchReason = ReadLaunchReason();
        var correlationId = ReadCorrelationId();
        var mcpLogPath = TryResolveMcpLogPath();
        var recentServerStarts = CountRecentServerStarts(mcpLogPath, ServerStartDedupWindow);
        var suppressServerStart = recentServerStarts > 0;

        if (!File.Exists(scriptPath))
        {
            Log(logPath, $"missing_script path={scriptPath}");
            return 1;
        }

        if (pythonExe is null)
        {
            Log(logPath, "missing_python executable");
            return 1;
        }

        using var stdin = Console.OpenStandardInput();
        using var stdout = Console.OpenStandardOutput();
        using var stderr = Console.OpenStandardError();

        var initialBuffer = new byte[81920];
        var initialRead = await TryReadInitialInputAsync(stdin, initialBuffer, InitialInputTimeout).ConfigureAwait(false);
        if (initialRead is null)
        {
            var snapshot = TryCaptureSiblingSnapshot(parentPid, currentPid, currentExeName);
            Log(logPath, $"initial_input_timeout timeoutSeconds={InitialInputTimeout.TotalSeconds:0} parentPid={parentPid} siblingCount={snapshot?.SiblingCount ?? 0} siblingRank={snapshot?.Rank ?? 0} launchReason={launchReason} correlationId={Sanitize(correlationId ?? "none")} wrapperHash={wrapperHash}");
            return 0;
        }

        if (initialRead.Value <= 0)
        {
            Log(logPath, "stdin_closed_before_initialize");
            return 0;
        }

        var startupSnapshot = TryCaptureSiblingSnapshot(parentPid, currentPid, currentExeName);
        if (startupSnapshot is not null)
        {
            Log(
                logPath,
                $"wrapper_initialized parentPid={startupSnapshot.ParentPid} siblingCount={startupSnapshot.SiblingCount} siblingRank={startupSnapshot.Rank} keepLimit={startupSnapshot.KeepLimit} duplicateMonitorEnabled={DuplicateMonitorEnabled} launchReason={launchReason} correlationId={Sanitize(correlationId ?? "none")} pluginRoot={Sanitize(pluginRoot)} wrapperHash={wrapperHash} suppressServerStart={suppressServerStart} recentServerStarts={recentServerStarts}"
            );
        }

        var psi = new ProcessStartInfo
        {
            FileName = pythonExe,
            Arguments = Quote(scriptPath),
            WorkingDirectory = pluginRoot,
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardInput = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
        };

        psi.Environment["PYTHONUTF8"] = "1";
        psi.Environment["PROJECT_MANAGER_WRAPPER_PARENT_PID"] = parentPid.ToString();
        psi.Environment["PROJECT_MANAGER_WRAPPER_PATH"] = wrapperPath;
        psi.Environment["PROJECT_MANAGER_WRAPPER_HASH"] = wrapperHash;
        psi.Environment["PROJECT_MANAGER_WRAPPER_LAUNCH_REASON"] = launchReason;
        psi.Environment["PROJECT_MANAGER_WRAPPER_CORRELATION_ID"] = correlationId ?? string.Empty;
        psi.Environment["PROJECT_MANAGER_WRAPPER_SUPPRESS_SERVER_START"] = suppressServerStart ? "1" : "0";
        psi.Environment["PROJECT_MANAGER_RESOLVED_PLUGIN_ROOT"] = pluginRoot;
        if (!string.IsNullOrWhiteSpace(mcpLogPath))
        {
            psi.Environment["PROJECT_MANAGER_MCP_LOG"] = mcpLogPath!;
        }

        using var process = new Process { StartInfo = psi, EnableRaisingEvents = true };
        try
        {
            if (!process.Start())
            {
                Log(logPath, "process_start_failed");
                return 1;
            }
        }
        catch (Exception ex)
        {
            Log(logPath, $"process_start_exception type={ex.GetType().Name} message={Sanitize(ex.Message)}");
            return 1;
        }

        Log(
            logPath,
            $"server_start pid={process.Id} python={pythonExe} script={scriptPath} parentPid={parentPid} pluginRoot={Sanitize(pluginRoot)} wrapperPath={Sanitize(wrapperPath)} wrapperHash={wrapperHash} launchReason={launchReason} correlationId={Sanitize(correlationId ?? "none")} suppressServerStart={suppressServerStart} recentServerStarts={recentServerStarts}"
        );

        long lastActivityTicks = DateTimeOffset.UtcNow.UtcTicks;
        MarkActivity(ref lastActivityTicks);

        var stdinTask = Task.Run(() =>
        {
            try
            {
                process.StandardInput.BaseStream.Write(initialBuffer, 0, initialRead.Value);
                process.StandardInput.BaseStream.Flush();
                MarkActivity(ref lastActivityTicks);
                CopySynchronously(
                    stdin,
                    process.StandardInput.BaseStream,
                    flushEachWrite: true,
                    onBytesTransferred: _ => MarkActivity(ref lastActivityTicks)
                );
            }
            catch (Exception ex)
            {
                Log(logPath, $"stdin_bridge_error type={ex.GetType().Name} message={Sanitize(ex.Message)}");
            }
            finally
            {
                try { process.StandardInput.Close(); } catch { }
            }
        });

        var stdoutTask = Task.Run(() =>
        {
            try
            {
                CopySynchronously(
                    process.StandardOutput.BaseStream,
                    stdout,
                    flushEachWrite: true,
                    onBytesTransferred: _ => MarkActivity(ref lastActivityTicks)
                );
            }
            catch (Exception ex)
            {
                Log(logPath, $"stdout_bridge_error type={ex.GetType().Name} message={Sanitize(ex.Message)}");
            }
        });

        var stderrTask = Task.Run(() =>
        {
            try
            {
                CopySynchronously(
                    process.StandardError.BaseStream,
                    stderr,
                    flushEachWrite: true,
                    onBytesTransferred: _ => MarkActivity(ref lastActivityTicks)
                );
            }
            catch (Exception ex)
            {
                Log(logPath, $"stderr_bridge_error type={ex.GetType().Name} message={Sanitize(ex.Message)}");
            }
        });

        var duplicateMonitorTask = Task.Run(async () =>
        {
            if (!DuplicateMonitorEnabled || parentPid <= 0)
            {
                return;
            }

            while (!process.HasExited)
            {
                try
                {
                    await Task.Delay(DuplicateMonitorPollInterval).ConfigureAwait(false);
                }
                catch
                {
                    return;
                }

                if (process.HasExited)
                {
                    return;
                }

                var snapshot = TryCaptureSiblingSnapshot(parentPid, currentPid, currentExeName);
                if (snapshot is null || !snapshot.IsOverflowDuplicate)
                {
                    continue;
                }

                var idleSeconds = (DateTimeOffset.UtcNow.UtcTicks - Interlocked.Read(ref lastActivityTicks)) / TimeSpan.TicksPerSecond;
                if (idleSeconds < DuplicateIdleThreshold.TotalSeconds)
                {
                    continue;
                }

                Log(
                    logPath,
                    $"duplicate_idle_exit parentPid={snapshot.ParentPid} siblingCount={snapshot.SiblingCount} siblingRank={snapshot.Rank} keepLimit={snapshot.KeepLimit} idleSeconds={idleSeconds}"
                );
                TryTerminateProcess(process);
                return;
            }
        });

        await process.WaitForExitAsync().ConfigureAwait(false);
        await Task.WhenAny(Task.WhenAll(stdoutTask, stderrTask, duplicateMonitorTask), Task.Delay(TimeSpan.FromSeconds(1))).ConfigureAwait(false);
        Log(logPath, $"server_stop pid={process.Id} exit={process.ExitCode}");
        return process.ExitCode;
    }

    private static string ReadLaunchReason()
    {
        var explicitReason = Environment.GetEnvironmentVariable("PROJECT_MANAGER_WRAPPER_LAUNCH_REASON");
        if (!string.IsNullOrWhiteSpace(explicitReason))
        {
            return Sanitize(explicitReason.Trim());
        }

        return "stdio_rpc";
    }

    private static string? ReadCorrelationId()
    {
        var candidates = new[]
        {
            Environment.GetEnvironmentVariable("PROJECT_MANAGER_WRAPPER_CORRELATION_ID"),
            Environment.GetEnvironmentVariable("PROJECT_MANAGER_SESSION_ID"),
            Environment.GetEnvironmentVariable("PROJECT_MANAGER_TURN_ID"),
            Environment.GetEnvironmentVariable("CODEX_SESSION_ID"),
            Environment.GetEnvironmentVariable("CODEX_TURN_ID"),
        };

        foreach (var candidate in candidates)
        {
            if (!string.IsNullOrWhiteSpace(candidate))
            {
                return Sanitize(candidate.Trim());
            }
        }

        return null;
    }

    private static async Task<int?> TryReadInitialInputAsync(Stream stdin, byte[] buffer, TimeSpan timeout)
    {
        var readTask = stdin.ReadAsync(buffer, 0, buffer.Length);
        var completed = await Task.WhenAny(readTask, Task.Delay(timeout)).ConfigureAwait(false);
        if (!ReferenceEquals(completed, readTask))
        {
            return null;
        }

        return await readTask.ConfigureAwait(false);
    }

    private static void CopySynchronously(Stream source, Stream destination, bool flushEachWrite, Action<int>? onBytesTransferred = null)
    {
        var buffer = new byte[81920];
        while (true)
        {
            var read = source.Read(buffer, 0, buffer.Length);
            if (read <= 0)
            {
                break;
            }

            destination.Write(buffer, 0, read);
            if (flushEachWrite)
            {
                destination.Flush();
            }

            onBytesTransferred?.Invoke(read);
        }

        if (!flushEachWrite)
        {
            destination.Flush();
        }
    }

    private static void TryTerminateProcess(Process process)
    {
        try
        {
            if (process.HasExited)
            {
                return;
            }

            process.Kill(entireProcessTree: true);
        }
        catch
        {
        }
    }

    private static void MarkActivity(ref long lastActivityTicks)
    {
        Interlocked.Exchange(ref lastActivityTicks, DateTimeOffset.UtcNow.UtcTicks);
    }

    private static int ReadPositiveIntEnv(string name, int fallback)
    {
        var rawValue = Environment.GetEnvironmentVariable(name);
        return int.TryParse(rawValue, out var parsed) && parsed > 0 ? parsed : fallback;
    }

    private static bool ReadBoolEnv(string name, bool fallback)
    {
        var rawValue = Environment.GetEnvironmentVariable(name);
        if (string.IsNullOrWhiteSpace(rawValue))
        {
            return fallback;
        }

        if (bool.TryParse(rawValue, out var parsed))
        {
            return parsed;
        }

        var normalized = rawValue.Trim().ToLowerInvariant();
        return normalized switch
        {
            "1" => true,
            "0" => false,
            "yes" => true,
            "no" => false,
            "on" => true,
            "off" => false,
            _ => fallback,
        };
    }

    private static string? ResolvePythonExe()
    {
        var candidates = new[]
        {
            Environment.GetEnvironmentVariable("PROJECT_MANAGER_PYTHON"),
            Environment.GetEnvironmentVariable("PYTHON_EXECUTABLE"),
            Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "Programs",
                "Python",
                "Python312",
                "python.exe"
            ),
            "python.exe",
        };

        foreach (var candidate in candidates)
        {
            if (string.IsNullOrWhiteSpace(candidate))
            {
                continue;
            }

            if (Path.IsPathRooted(candidate))
            {
                if (File.Exists(candidate))
                {
                    return candidate;
                }

                continue;
            }

            var resolved = ResolveFromPath(candidate);
            if (resolved is not null)
            {
                return resolved;
            }
        }

        return null;
    }

    private static string? ResolveFromPath(string executableName)
    {
        var pathValue = Environment.GetEnvironmentVariable("PATH");
        if (string.IsNullOrWhiteSpace(pathValue))
        {
            return null;
        }

        foreach (var segment in pathValue.Split(Path.PathSeparator, StringSplitOptions.RemoveEmptyEntries))
        {
            try
            {
                var candidate = Path.Combine(segment.Trim(), executableName);
                if (File.Exists(candidate))
                {
                    return candidate;
                }
            }
            catch
            {
            }
        }

        return null;
    }

    private static int TryGetParentProcessId()
    {
        foreach (var processEntry in SnapshotProcesses())
        {
            if (processEntry.ProcessId == Environment.ProcessId)
            {
                return processEntry.ParentProcessId;
            }
        }

        return -1;
    }

    private static SiblingSnapshot? TryCaptureSiblingSnapshot(int parentPid, int currentPid, string currentExeName)
    {
        if (parentPid <= 0 || string.IsNullOrWhiteSpace(currentExeName))
        {
            return null;
        }

        var siblings = SnapshotProcesses()
            .Where(entry => entry.ParentProcessId == parentPid && string.Equals(entry.ExeFile, currentExeName, StringComparison.OrdinalIgnoreCase))
            .Select(entry => ToSiblingRuntime(entry.ProcessId))
            .Where(entry => entry is not null)
            .Cast<SiblingRuntime>()
            .OrderBy(entry => entry.StartTimeUtc)
            .ThenBy(entry => entry.ProcessId)
            .ToList();

        if (siblings.Count == 0)
        {
            return null;
        }

        var rank = siblings.FindIndex(entry => entry.ProcessId == currentPid);
        if (rank < 0)
        {
            return null;
        }

        return new SiblingSnapshot(
            ParentPid: parentPid,
            CurrentPid: currentPid,
            SiblingCount: siblings.Count,
            Rank: rank + 1,
            KeepLimit: SafeSiblingLimit,
            SiblingPids: siblings.Select(entry => entry.ProcessId).ToArray()
        );
    }

    private static SiblingRuntime? ToSiblingRuntime(int pid)
    {
        try
        {
            using var process = Process.GetProcessById(pid);
            DateTimeOffset startTimeUtc;
            try
            {
                startTimeUtc = new DateTimeOffset(process.StartTime.ToUniversalTime());
            }
            catch
            {
                startTimeUtc = DateTimeOffset.MaxValue;
            }

            return new SiblingRuntime(pid, startTimeUtc);
        }
        catch
        {
            return null;
        }
    }

    private static List<ProcessSnapshot> SnapshotProcesses()
    {
        var snapshot = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
        if (snapshot == InvalidHandleValue)
        {
            return [];
        }

        try
        {
            var entries = new List<ProcessSnapshot>();
            var processEntry = new PROCESSENTRY32
            {
                dwSize = (uint)Marshal.SizeOf<PROCESSENTRY32>(),
            };

            if (!Process32First(snapshot, ref processEntry))
            {
                return entries;
            }

            do
            {
                entries.Add(
                    new ProcessSnapshot(
                        ProcessId: unchecked((int)processEntry.th32ProcessID),
                        ParentProcessId: unchecked((int)processEntry.th32ParentProcessID),
                        ExeFile: processEntry.szExeFile ?? string.Empty
                    )
                );
                processEntry.dwSize = (uint)Marshal.SizeOf<PROCESSENTRY32>();
            }
            while (Process32Next(snapshot, ref processEntry));

            return entries;
        }
        finally
        {
            CloseHandle(snapshot);
        }
    }

    private static string? TryResolveWrapperLogPath()
    {
        try
        {
            return ResolveWrapperLogPath();
        }
        catch
        {
            return null;
        }
    }

    private static string? TryResolveMcpLogPath()
    {
        var explicitPath = Environment.GetEnvironmentVariable("PROJECT_MANAGER_MCP_LOG");
        return string.IsNullOrWhiteSpace(explicitPath) ? null : explicitPath;
    }

    private static int CountRecentServerStarts(string? logPath, TimeSpan window)
    {
        if (string.IsNullOrWhiteSpace(logPath) || !File.Exists(logPath))
        {
            return 0;
        }

        try
        {
            var cutoff = DateTimeOffset.UtcNow - window;
            var lines = File.ReadLines(logPath);
            var count = 0;
            foreach (var line in lines.Reverse().Take(200))
            {
                if (string.IsNullOrWhiteSpace(line))
                {
                    continue;
                }

                using var document = JsonDocument.Parse(line);
                var root = document.RootElement;
                if (!root.TryGetProperty("event", out var eventNode) || eventNode.ValueKind != JsonValueKind.String)
                {
                    continue;
                }

                if (!string.Equals(eventNode.GetString(), "server_start", StringComparison.Ordinal))
                {
                    continue;
                }

                if (!root.TryGetProperty("time", out var timeNode) || timeNode.ValueKind != JsonValueKind.String)
                {
                    continue;
                }

                if (!DateTimeOffset.TryParse(timeNode.GetString(), out var eventTime))
                {
                    continue;
                }

                if (eventTime < cutoff)
                {
                    break;
                }

                count++;
            }

            return count;
        }
        catch
        {
            return 0;
        }
    }

    private static string ResolveWrapperLogPath()
    {
        var explicitPath = Environment.GetEnvironmentVariable("PROJECT_MANAGER_WRAPPER_LOG");
        if (!string.IsNullOrWhiteSpace(explicitPath))
        {
            var directory = Path.GetDirectoryName(explicitPath);
            if (!string.IsNullOrWhiteSpace(directory))
            {
                Directory.CreateDirectory(directory);
            }

            return explicitPath;
        }

        var defaultDir = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "Codex",
            "project-manager"
        );
        Directory.CreateDirectory(defaultDir);
        return Path.Combine(defaultDir, "project-manager-mcp-wrapper.log");
    }

    private static void Log(string? logPath, string message)
    {
        if (string.IsNullOrWhiteSpace(logPath))
        {
            return;
        }

        var line = $"{DateTimeOffset.UtcNow:O} {message}{Environment.NewLine}";
        if (TryAppend(logPath, line))
        {
            return;
        }

        var fallbackPath = TryBuildFallbackLogPath(logPath);
        if (!string.IsNullOrWhiteSpace(fallbackPath) && !string.Equals(fallbackPath, logPath, StringComparison.OrdinalIgnoreCase))
        {
            TryAppend(fallbackPath, line);
        }
    }

    private static bool TryAppend(string path, string line)
    {
        try
        {
            var directory = Path.GetDirectoryName(path);
            if (!string.IsNullOrWhiteSpace(directory))
            {
                Directory.CreateDirectory(directory);
            }

            lock (LogLock)
            {
                using var stream = new FileStream(path, FileMode.Append, FileAccess.Write, FileShare.ReadWrite | FileShare.Delete);
                using var writer = new StreamWriter(stream, new UTF8Encoding(false));
                writer.Write(line);
                writer.Flush();
            }

            return true;
        }
        catch
        {
            return false;
        }
    }

    private static string? TryBuildFallbackLogPath(string preferredPath)
    {
        try
        {
            var directory = Path.GetDirectoryName(preferredPath);
            if (string.IsNullOrWhiteSpace(directory))
            {
                directory = Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                    "Codex",
                    "project-manager"
                );
            }

            Directory.CreateDirectory(directory);
            return Path.Combine(directory, $"project-manager-mcp-wrapper-fallback-{Environment.ProcessId}.log");
        }
        catch
        {
            return null;
        }
    }

    private static string Quote(string value)
    {
        if (value.Contains('"'))
        {
            value = value.Replace("\"", "\\\"");
        }

        return $"\"{value}\"";
    }

    private static string Sanitize(string value) => value.Replace(Environment.NewLine, " ").Replace('\n', ' ').Replace('\r', ' ');

    private static string? TryComputeFileHash(string path)
    {
        try
        {
            if (!File.Exists(path))
            {
                return null;
            }

            using var stream = File.OpenRead(path);
            var hash = SHA256.HashData(stream);
            return Convert.ToHexString(hash).ToLowerInvariant();
        }
        catch
        {
            return null;
        }
    }

    private readonly record struct ProcessSnapshot(int ProcessId, int ParentProcessId, string ExeFile);

    private readonly record struct SiblingRuntime(int ProcessId, DateTimeOffset StartTimeUtc);

    private sealed record SiblingSnapshot(
        int ParentPid,
        int CurrentPid,
        int SiblingCount,
        int Rank,
        int KeepLimit,
        IReadOnlyList<int> SiblingPids
    )
    {
        public bool IsOverflowDuplicate => SiblingCount > KeepLimit && Rank > KeepLimit;
    }

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Auto)]
    private struct PROCESSENTRY32
    {
        public uint dwSize;
        public uint cntUsage;
        public uint th32ProcessID;
        public IntPtr th32DefaultHeapID;
        public uint th32ModuleID;
        public uint cntThreads;
        public uint th32ParentProcessID;
        public int pcPriClassBase;
        public uint dwFlags;

        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = MaxExeNameChars)]
        public string szExeFile;
    }

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern IntPtr CreateToolhelp32Snapshot(uint dwFlags, uint th32ProcessID);

    [DllImport("kernel32.dll", CharSet = CharSet.Auto, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool Process32First(IntPtr hSnapshot, ref PROCESSENTRY32 lppe);

    [DllImport("kernel32.dll", CharSet = CharSet.Auto, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool Process32Next(IntPtr hSnapshot, ref PROCESSENTRY32 lppe);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool CloseHandle(IntPtr hObject);
}
