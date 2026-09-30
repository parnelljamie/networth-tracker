// Passbook for Android (docs/07-mobile.md "Android shell"): a WebView around the same FastAPI
// backend and React UI as the PC, run on the phone by Chaquopy.
pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}

rootProject.name = "Passbook"
include(":app")
