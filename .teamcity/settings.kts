// TeamCity Kotlin DSL — configuration artifact (ADR-001).
// No TeamCity server is available on this machine; this file has NOT been
// applied to a live server and is not claimed as a verified pipeline.
import jetbrains.buildServer.configs.kotlin.*
import jetbrains.buildServer.configs.kotlin.buildSteps.script

version = "2024.1"

object GitHubRoot : VcsRoot({
    name = "Instant Mechanic GitHub"
    url = "https://github.com/akcodes-py/Instant-Mechanic-AI-Diagonistic-Bot.git"
    branch = "main"
})

object BackendTests : BuildType({
    name = "Backend - pytest"
    vcs { root(GitHubRoot) }
    steps {
        script {
            name = "pytest"
            scriptContent = """
                python -m pip install -r backend/requirements.txt
                python -m pytest -q
            """.trimIndent()
        }
    }
})

object DispatchTests : BuildType({
    name = "Dispatch - JUnit 5"
    vcs { root(GitHubRoot) }
    steps {
        script {
            name = "gradle test"
            scriptContent = """
                cd dispatch-service
                ./gradlew test --no-daemon --console=plain
            """.trimIndent()
        }
    }
})

object FrontendChecks : BuildType({
    name = "Frontend - lint, typecheck, build"
    vcs { root(GitHubRoot) }
    steps {
        script {
            name = "npm gates"
            scriptContent = """
                npm install
                npm run lint
                npm run typecheck
                npm run build
            """.trimIndent()
        }
    }
})

object ComposeConfig : BuildType({
    name = "Infra - docker compose config"
    vcs { root(GitHubRoot) }
    steps {
        script {
            name = "validate compose"
            scriptContent = "docker compose config --quiet"
        }
    }
})

project {
    name = "Instant Mechanic - H3 Dispatch"
    vcsRoot(GitHubRoot)
    buildType(BackendTests)
    buildType(DispatchTests)
    buildType(FrontendChecks)
    buildType(ComposeConfig)
}
