@echo off
setlocal enabledelayedexpansion

:: === Office Werewolf Launcher ===

set PYTHONIOENCODING=utf-8
set PROJECT_DIR=%~dp0
cd /d "%PROJECT_DIR%"

:: --- venv activation ---
if exist "%PROJECT_DIR%.venv\Scripts\activate.bat" call "%PROJECT_DIR%.venv\Scripts\activate.bat" & goto :VENV_DONE
if exist "%PROJECT_DIR%venv\Scripts\activate.bat" call "%PROJECT_DIR%venv\Scripts\activate.bat" & goto :VENV_DONE
echo [INFO] No venv detected, using system Python

:VENV_DONE

:: --- ensure output dirs ---
if not exist "exports" mkdir exports
if not exist "reports" mkdir reports
if not exist "winrate" mkdir winrate
if not exist "evolution" mkdir evolution

goto MENU

:: --- timestamp subroutine ---
:GET_TIMESTAMP
for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value 2^>nul') do set DATETIME=%%I
set TIMESTAMP=%DATETIME:~0,8%_%DATETIME:~8,6%
goto :EOF

:: ============================
:: MENU
:: ============================
:MENU
cls
echo ========================================
echo   Office Werewolf - Launcher
echo ========================================
echo(
echo   1.  Run single game
echo   2.  Batch run
echo   3.  A/B experiment
echo   4.  Evaluate game log
echo   5.  Skills evolution
echo   6.  Environment check
echo   7.  Run tests
echo   0.  Exit
echo(
set "choice="
set /p "choice=Select: "

if "%choice%"=="1" goto RUN_GAME
if "%choice%"=="2" goto BATCH_RUN
if "%choice%"=="3" goto AB_EXPERIMENT
if "%choice%"=="4" goto EVALUATE
if "%choice%"=="5" goto SKILLS_EVOLUTION
if "%choice%"=="6" goto ENV_CHECK
if "%choice%"=="7" goto RUN_TESTS
if "%choice%"=="0" goto END
goto MENU

:: ============================
:: 1. Run single game
:: ============================
:RUN_GAME
cls
echo --- Run single game ---
echo(

set "PLAYERS="
set /p "PLAYERS=Players (6/9/12, default 12): "
if "%PLAYERS%"=="" set PLAYERS=12

set "PROMPT_VER="
set /p "PROMPT_VER=Prompt version (v2, default v2): "
if "%PROMPT_VER%"=="" set PROMPT_VER=v2

set "SKILLS_VER="
set /p "SKILLS_VER=Skills version (empty=none, e.g. evo_1): "

set "SKILLS_TARGETS="
if not "%SKILLS_VER%"=="" (
    set /p "SKILLS_TARGETS=Skills targets (all/faction:spy/seat:1,3,5, default all): "
    if "!SKILLS_TARGETS!"=="" set SKILLS_TARGETS=all
)

set "HUMAN_SEAT="
set /p "HUMAN_SEAT=Human seat (e.g. 3, empty=all AI): "

set "AGENT_VER_GAME="
set /p "AGENT_VER_GAME=Agent version tag (empty=baseline): "
if "%AGENT_VER_GAME%"=="" set AGENT_VER_GAME=baseline

call :GET_TIMESTAMP
set "LOG_PREFIX=exports/game_%PLAYERS%p_%TIMESTAMP%"

set "CMD_PART1=python main_cn.py --players %PLAYERS% --prompt-version %PROMPT_VER%"
set "CMD_PART2=--log %LOG_PREFIX% --agent-version %AGENT_VER_GAME%"
set "FULL_CMD=%CMD_PART1% %CMD_PART2%"
if not "%SKILLS_VER%"=="" set "FULL_CMD=%FULL_CMD% --skills-version %SKILLS_VER% --skills-targets %SKILLS_TARGETS%"
if not "%HUMAN_SEAT%"=="" set "FULL_CMD=%FULL_CMD% --human-seat %HUMAN_SEAT%"

echo(
echo ^> %FULL_CMD%
echo(
%FULL_CMD%

echo(
pause
goto MENU

:: ============================
:: 2. Batch run
:: ============================
:BATCH_RUN
cls
echo --- Batch run ---
echo(

set "NUM_GAMES="
set /p "NUM_GAMES=Num games (default 3): "
if "%NUM_GAMES%"=="" set NUM_GAMES=3

set "PLAYERS="
set /p "PLAYERS=Players (default 12): "
if "%PLAYERS%"=="" set PLAYERS=12

set "PROMPT_VER="
set /p "PROMPT_VER=Prompt version (default v2): "
if "%PROMPT_VER%"=="" set PROMPT_VER=v2

set "SKILLS_VER_BATCH="
set /p "SKILLS_VER_BATCH=Skills version (empty=none, e.g. evo_1): "

set "SKILLS_TARGETS_BATCH="
if not "%SKILLS_VER_BATCH%"=="" (
    set /p "SKILLS_TARGETS_BATCH=Skills targets (all/faction:spy/seat:1,3,5, default all): "
    if "!SKILLS_TARGETS_BATCH!"=="" set SKILLS_TARGETS_BATCH=all
)

call :GET_TIMESTAMP
set "LOG_DIR=exports/batch_%TIMESTAMP%"

if not "%SKILLS_VER_BATCH%"=="" (
    echo(
    echo ^> python batch_runner.py --num-games %NUM_GAMES% --players %PLAYERS% --prompt-version %PROMPT_VER% --log-dir %LOG_DIR% --skills-version %SKILLS_VER_BATCH% --skills-targets %SKILLS_TARGETS_BATCH%
    echo(
    python batch_runner.py --num-games %NUM_GAMES% --players %PLAYERS% --prompt-version %PROMPT_VER% --log-dir "%LOG_DIR%" --skills-version %SKILLS_VER_BATCH% --skills-targets %SKILLS_TARGETS_BATCH%
) else (
    echo(
    echo ^> python batch_runner.py --num-games %NUM_GAMES% --players %PLAYERS% --prompt-version %PROMPT_VER% --log-dir %LOG_DIR%
    echo(
    python batch_runner.py --num-games %NUM_GAMES% --players %PLAYERS% --prompt-version %PROMPT_VER% --log-dir "%LOG_DIR%"
)

echo(
pause
goto MENU

:: ============================
:: 3. A/B experiment
:: ============================
:AB_EXPERIMENT
cls
echo --- A/B experiment ---
echo(

set "VERSION_A="
set /p "VERSION_A=Prompt version A (default v2): "
if "%VERSION_A%"=="" set VERSION_A=v2

set "VERSION_B="
set /p "VERSION_B=Prompt version B (default v2): "
if "%VERSION_B%"=="" set VERSION_B=v2

set "SKILLS_VER_A="
set /p "SKILLS_VER_A=Skills version A (empty=none, e.g. evo_1): "

set "SKILLS_VER_B="
set /p "SKILLS_VER_B=Skills version B (empty=none, e.g. evo_2): "

set "SKILLS_TARGETS_AB="
if not "%SKILLS_VER_A%"=="" (
    set /p "SKILLS_TARGETS_AB=Skills targets (all/faction:spy/seat:1,3,5, default all): "
    if "!SKILLS_TARGETS_AB!"=="" set SKILLS_TARGETS_AB=all
)

set "NUM_GAMES="
set /p "NUM_GAMES=Games per version (default 3): "
if "%NUM_GAMES%"=="" set NUM_GAMES=3

set "PLAYERS="
set /p "PLAYERS=Players (default 12): "
if "%PLAYERS%"=="" set PLAYERS=12

:: Build A/B command with skills support
set "AB_CMD=python ab_experiment.py --version-a %VERSION_A% --version-b %VERSION_B% --num-games %NUM_GAMES% --players %PLAYERS%"
if not "%SKILLS_VER_A%"=="" set "AB_CMD=%AB_CMD% --skills-version-a %SKILLS_VER_A%"
if not "%SKILLS_VER_B%"=="" set "AB_CMD=%AB_CMD% --skills-version-b %SKILLS_VER_B%"
if not "%SKILLS_TARGETS_AB%"=="" set "AB_CMD=%AB_CMD% --skills-targets %SKILLS_TARGETS_AB%"

echo(
echo ^> %AB_CMD%
echo(
%AB_CMD%

echo(
pause
goto MENU

:: ============================
:: 4. Evaluate game log
:: ============================
:EVALUATE
cls
echo --- Evaluate game log ---
echo(

:: demo bad case?
set "DEMO_BAD="
set /p "DEMO_BAD=Use built-in bad-case demo? (y/n, default n): "
if /i "%DEMO_BAD%"=="y" (
    set "AGENT_VER="
    set /p "AGENT_VER=Agent version tag (default baseline): "
    if "%AGENT_VER%"=="" set AGENT_VER=baseline
    echo(
    echo ^> python evaluation_cn.py --demo-bad-case --agent-version %AGENT_VER%
    echo(
    python evaluation_cn.py --demo-bad-case --agent-version %AGENT_VER%
    echo(
    echo Report saved to reports\
    pause
    goto MENU
)

:: compare versions?
set "COMPARE_MODE="
set /p "COMPARE_MODE=Compare versions? (y/n, default n): "
if /i "%COMPARE_MODE%"=="y" (
    set "V1_DIR="
    set /p "V1_DIR=Version 1 dir (e.g. exports/v2): "
    set "V2_DIR="
    set /p "V2_DIR=Version 2 dir (e.g. exports/v3): "
    echo(
    echo ^> python evaluation_cn.py --compare-versions "%V1_DIR%" "%V2_DIR%"
    echo(
    python evaluation_cn.py --compare-versions "%V1_DIR%" "%V2_DIR%"
    echo(
    echo Report saved to reports\
    pause
    goto MENU
)

:: regular evaluation
echo Available .jsonl logs:
echo ----------------------------------------
set FILE_COUNT=0
for %%F in (exports\*.jsonl) do (
    set /a FILE_COUNT+=1
    echo   !FILE_COUNT!. %%F
)
if !FILE_COUNT!==0 (
    echo   No .jsonl logs found, run a game first
)
echo ----------------------------------------
echo(

set "LOG_FILE="
set /p "LOG_FILE=Log file path (e.g. exports/game_12p_20260601_120000.jsonl): "
if "%LOG_FILE%"=="" echo No file specified, back to menu & pause & goto MENU

:: log path validation
if not exist "%LOG_FILE%" (
    echo %LOG_FILE% | findstr /r "^[0-9]*$" >nul 2>&1
    if not errorlevel 1 (
        set "FOUND_FILE="
        for %%F in (exports\*%LOG_FILE%*.jsonl) do set "FOUND_FILE=%%F"
        if defined FOUND_FILE (
            set "LOG_FILE=!FOUND_FILE!"
            echo   Auto-resolved to: !LOG_FILE!
        ) else (
            echo   ERROR: No log file matching %LOG_FILE%
            pause
            goto MENU
        )
    ) else (
        echo   ERROR: File not found: %LOG_FILE%
        echo   Hint: use full path like exports/game_12p_20260601_120000.jsonl
        pause
        goto MENU
    )
)

set "AGENT_VER="
set /p "AGENT_VER=Agent version tag (default baseline): "
if "%AGENT_VER%"=="" set AGENT_VER=baseline

set "LLM_JUDGE="
set /p "LLM_JUDGE=Enable LLM judge? (y/n, default y): "
if "%LLM_JUDGE%"=="" set LLM_JUDGE=y

if /i "%LLM_JUDGE%"=="y" (
    set "LLM_SAMPLE_RATE="
    set /p "LLM_SAMPLE_RATE=LLM sample rate (0-1, default 1.0): "
    if "%LLM_SAMPLE_RATE%"=="" set LLM_SAMPLE_RATE=1.0

    set "EVAL_MODEL="
    set /p "EVAL_MODEL=Eval model name (empty=default qwen-max): "

    set "EVAL_STRATEGY="
    set /p "EVAL_STRATEGY=Sample strategy (uniform/critical_first/role_balanced, default uniform): "
    if "%EVAL_STRATEGY%"=="" set EVAL_STRATEGY=uniform

    set "EVAL_CMD=python evaluation_cn.py --log "%LOG_FILE%" --agent-version %AGENT_VER% --enable-llm-judge --llm-sample-rate %LLM_SAMPLE_RATE% --eval-sample-strategy %EVAL_STRATEGY%"
    if not "%EVAL_MODEL%"=="" set "EVAL_CMD=!EVAL_CMD! --eval-model %EVAL_MODEL%"

    echo(
    echo ^> !EVAL_CMD!
    echo(
    !EVAL_CMD!
) else (
    echo(
    echo ^> python evaluation_cn.py --log "%LOG_FILE%" --agent-version %AGENT_VER%
    echo(
    python evaluation_cn.py --log "%LOG_FILE%" --agent-version %AGENT_VER%
)

echo(
echo Report saved to reports\
pause
goto MENU

:: ============================
:: 5. Skills evolution
:: ============================
:SKILLS_EVOLUTION
cls
echo --- Skills evolution ---
echo(
echo   a) Generate skills from report
echo   b) Run evolution loop
echo   c) Evaluate skills version
echo   d) View evolution history
echo   e) View winrate stats
echo   f) Back to menu
echo(
set "skill_choice="
set /p "skill_choice=Select: "

if /i "%skill_choice%"=="a" goto SKILLS_GENERATE
if /i "%skill_choice%"=="b" goto SKILLS_EVOLVE
if /i "%skill_choice%"=="c" goto SKILLS_EVAL
if /i "%skill_choice%"=="d" goto SKILLS_HISTORY
if /i "%skill_choice%"=="e" goto SKILLS_STATS
if /i "%skill_choice%"=="f" goto MENU
goto SKILLS_EVOLUTION

:SKILLS_GENERATE
set "REPORT_FILE="
set /p "REPORT_FILE=Report path (e.g. reports/evaluation_report_xxx.json): "
if "%REPORT_FILE%"=="" echo No report specified & pause & goto SKILLS_EVOLUTION

set "SKILLS_VER="
set /p "SKILLS_VER=New version name (e.g. evo_2): "
if "%SKILLS_VER%"=="" echo No version name & pause & goto SKILLS_EVOLUTION

set "NO_LLM_GEN="
set /p "NO_LLM_GEN=Disable LLM refinement? (y/n, default n=use LLM): "

if /i "%NO_LLM_GEN%"=="y" (
    echo(
    echo ^> python evolution.py generate --from-report "%REPORT_FILE%" --version %SKILLS_VER% --no-llm
    echo(
    python evolution.py generate --from-report "%REPORT_FILE%" --version %SKILLS_VER% --no-llm
) else (
    echo(
    echo ^> python evolution.py generate --from-report "%REPORT_FILE%" --version %SKILLS_VER%
    echo(
    python evolution.py generate --from-report "%REPORT_FILE%" --version %SKILLS_VER%
)

echo(
pause
goto SKILLS_EVOLUTION

:SKILLS_EVOLVE
set "GENERATIONS="
set /p "GENERATIONS=Generations (default 5): "
if "%GENERATIONS%"=="" set GENERATIONS=5
set "GAMES_PER_GEN="
set /p "GAMES_PER_GEN=Games per gen (default 3): "
if "%GAMES_PER_GEN%"=="" set GAMES_PER_GEN=3
set "PLAYERS="
set /p "PLAYERS=Players (default 12): "
if "%PLAYERS%"=="" set PLAYERS=12

set "SKILLS_TARGETS_EVO="
set /p "SKILLS_TARGETS_EVO=Skills targets (all/faction:spy/seat:1,3,5, default all): "
if "%SKILLS_TARGETS_EVO%"=="" set SKILLS_TARGETS_EVO=all

set "EVO_NO_LLM="
set /p "EVO_NO_LLM=Disable LLM? (y=off both eval+refine, default n=full LLM pipeline): "

if /i "%EVO_NO_LLM%"=="y" (
    set "EVO_CMD=python evolution.py evolve --generations %GENERATIONS% --games-per-gen %GAMES_PER_GEN% --players %PLAYERS% --skills-targets %SKILLS_TARGETS_EVO% --no-llm"
) else (
    set "EVO_CMD=python evolution.py evolve --generations %GENERATIONS% --games-per-gen %GAMES_PER_GEN% --players %PLAYERS% --skills-targets %SKILLS_TARGETS_EVO% --enable-llm-judge"
)

echo(
echo ^> %EVO_CMD%
echo(
%EVO_CMD%

echo(
pause
goto SKILLS_EVOLUTION

:SKILLS_EVAL
set "SKILLS_VER="
set /p "SKILLS_VER=Skills version (e.g. evo_1): "
if "%SKILLS_VER%"=="" echo No version & pause & goto SKILLS_EVOLUTION

set "NUM_GAMES="
set /p "NUM_GAMES=Num games (default 5): "
if "%NUM_GAMES%"=="" set NUM_GAMES=5

set "PLAYERS="
set /p "PLAYERS=Players (default 12): "
if "%PLAYERS%"=="" set PLAYERS=12

set "EVAL_TARGETS="
set /p "EVAL_TARGETS=Skills targets (all/faction:spy/seat:1,3,5, default all): "
if "%EVAL_TARGETS%"=="" set EVAL_TARGETS=all

echo(
echo ^> python evolution.py evaluate --version %SKILLS_VER% --num-games %NUM_GAMES% --players %PLAYERS% --targets %EVAL_TARGETS%
echo(
python evolution.py evaluate --version %SKILLS_VER% --num-games %NUM_GAMES% --players %PLAYERS% --targets %EVAL_TARGETS%

echo(
pause
goto SKILLS_EVOLUTION

:SKILLS_HISTORY
echo(
python evolution.py history
echo(
pause
goto SKILLS_EVOLUTION

:SKILLS_STATS
set "GROUP_BY="
set /p "GROUP_BY=Group by (faction/role/skills/version, default faction): "
if "%GROUP_BY%"=="" set GROUP_BY=faction

set "SHOW_ALL="
set /p "SHOW_ALL=Show all stats? (y/n, default n): "

if /i "%SHOW_ALL%"=="y" (
    echo(
    echo ^> python evolution.py stats --group-by %GROUP_BY% --all
    echo(
    python evolution.py stats --group-by %GROUP_BY% --all
) else (
    echo(
    echo ^> python evolution.py stats --group-by %GROUP_BY%
    echo(
    python evolution.py stats --group-by %GROUP_BY%
)

echo(
pause
goto SKILLS_EVOLUTION

:: ============================
:: 6. Environment check
:: ============================
:ENV_CHECK
cls
echo --- Environment check ---
echo(
echo Python version:
python --version
echo(
echo .env file:
if exist ".env" (
    echo   Found
) else (
    echo   Not found - create .env with DASHSCOPE_API_KEY
)
echo(
echo Detailed env check:
python test_env.py
echo(
pause
goto MENU

:: ============================
:: 7. Run tests
:: ============================
:RUN_TESTS
cls
echo --- Run tests ---
echo(
echo   a) All tests
echo   b) Specific file
echo   c) Smoke tests
echo   d) Back to menu
echo(
set "test_choice="
set /p "test_choice=Select: "

if /i "%test_choice%"=="a" goto RUN_ALL_TESTS
if /i "%test_choice%"=="b" goto TEST_SPECIFIC_FILE
if /i "%test_choice%"=="c" goto RUN_SMOKE_TESTS
if /i "%test_choice%"=="d" goto MENU
goto RUN_TESTS

:RUN_ALL_TESTS
python -m pytest tests/ -v --tb=short
echo(
pause
goto MENU

:RUN_SMOKE_TESTS
echo Running core tests...
python -m pytest tests/test_voting.py tests/test_winning.py tests/test_skills.py tests/test_guard_protection_fix.py -v --tb=short -q
echo(
pause
goto MENU

:TEST_SPECIFIC_FILE
set "TEST_FILE="
set /p "TEST_FILE=Test file (e.g. tests/test_voting.py): "
python -m pytest %TEST_FILE% -v --tb=short
echo(
pause
goto MENU

:: ============================
:END
echo Bye!
endlocal