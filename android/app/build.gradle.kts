import java.io.File

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("com.chaquo.python")
}

val repoRoot: File = rootProject.projectDir.parentFile

// One version for every platform: backend/app/__init__.py's __version__ (0.1.2 -> code 102).
val appVersion: String = Regex("__version__ = \"([^\"]+)\"")
    .find(File(repoRoot, "backend/app/__init__.py").readText())!!
    .groupValues[1]
val appVersionCode: Int = appVersion.split(".").map { it.toInt() }.let { (major, minor, patch) ->
    major * 10000 + minor * 100 + patch
}

android {
    namespace = "com.passbook.app"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.passbook.app"
        minSdk = 26
        targetSdk = 35
        versionCode = appVersionCode
        versionName = appVersion
        ndk {
            // Phones. Add "x86_64" to run it in an emulator on a PC.
            abiFilters += listOf("arm64-v8a")
        }
    }

    // docs/07-mobile.md "Distribution": the Release workflow decodes the keystore from the
    // repository secrets, if set, and passes it in here. Every release must use the same key, or
    // Android refuses the upgrade. Without them the release APK is signed with the build
    // machine's debug key, so each release installs only after uninstalling the last one.
    val keystoreFile = System.getenv("ANDROID_KEYSTORE_FILE")
    signingConfigs {
        if (keystoreFile != null) {
            create("release") {
                storeFile = file(keystoreFile)
                storePassword = System.getenv("ANDROID_KEYSTORE_PASSWORD")
                keyAlias = System.getenv("ANDROID_KEY_ALIAS")
                keyPassword = System.getenv("ANDROID_KEY_PASSWORD")
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName(if (keystoreFile != null) "release" else "debug")
        }
    }

    buildFeatures {
        buildConfig = true
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    // backend/alembic, alembic.ini and frontend/dist, unpacked to private storage on first run.
    sourceSets["main"].assets.srcDir(layout.buildDirectory.dir("phone-assets"))
}

chaquopy {
    defaultConfig {
        version = "3.12"
        pip {
            // pydantic-core has no Android build anywhere, so android/wheels/build-pydantic-core.sh
            // compiles one into android/wheels/dist before the app is built.
            options("--find-links", rootProject.file("wheels/dist").absolutePath)
            install("-r", "requirements.txt")
        }
    }
    sourceSets {
        getByName("main") {
            srcDir("build/phone-python")
        }
    }
}

dependencies {
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("androidx.activity:activity-ktx:1.9.3")
    implementation("androidx.core:core-ktx:1.13.1")
    // QR scanning through Google Play services: no camera permission for this app.
    implementation("com.google.android.gms:play-services-code-scanner:16.1.0")
}

// The backend's `app` package, as-is.
val copyPython by tasks.registering(Sync::class) {
    from(File(repoRoot, "backend/app")) {
        exclude("**/__pycache__/**", "launcher.py")
    }
    into(layout.buildDirectory.dir("phone-python/app"))
}

// Read-only resources the backend finds through NW_RESOURCE_DIR (app/core/paths.py).
val copyResources by tasks.registering(Sync::class) {
    val dist = File(repoRoot, "frontend/dist")
    doFirst {
        check(File(dist, "index.html").exists()) { "Build the frontend first: cd frontend; npm run build" }
    }
    into(layout.buildDirectory.dir("phone-assets/resources"))
    from(File(repoRoot, "backend/alembic")) {
        into("backend/alembic")
        exclude("**/__pycache__/**")
    }
    from(File(repoRoot, "backend/alembic.ini")) {
        into("backend")
    }
    from(dist) {
        into("frontend/dist")
    }
}

tasks.named("preBuild") {
    dependsOn(copyPython, copyResources)
}

// Gradle checks that every task reading another's output says so, not just runs after it.
tasks.matching { it.name.startsWith("merge") && it.name.endsWith("PythonSources") }.configureEach {
    dependsOn(copyPython)
}
tasks.matching { it.name.startsWith("merge") && it.name.endsWith("Assets") }.configureEach {
    dependsOn(copyResources)
}
