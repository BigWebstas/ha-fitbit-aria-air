plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "net.webstas.ariahealth"
    compileSdk = 36

    defaultConfig {
        applicationId = "net.webstas.ariahealth"
        minSdk = 28
        targetSdk = 34
        versionCode = 2
        versionName = "0.2.0"
    }

    // Release signing uses a keystore kept outside the repo. Override the paths with
    // -PariaKeystore=... / -PariaKeystorePassFile=...; without a keystore the release
    // build is left unsigned.
    val keystore = file(
        providers.gradleProperty("ariaKeystore")
            .getOrElse("${System.getProperty("user.home")}/.android-release/aria-air.jks")
    )
    val passFile = file(
        providers.gradleProperty("ariaKeystorePassFile")
            .getOrElse("${System.getProperty("user.home")}/.android-release/aria-air.pass")
    )
    val canSign = keystore.exists() && passFile.exists()

    signingConfigs {
        if (canSign) {
            create("release") {
                val password = passFile.readText().trim()
                storeFile = keystore
                storePassword = password
                keyAlias = "aria-air"
                keyPassword = password
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            if (canSign) signingConfig = signingConfigs.getByName("release")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    packaging {
        resources {
            excludes += setOf(
                "META-INF/INDEX.LIST",
                "META-INF/io.netty.versions.properties",
                "META-INF/DEPENDENCIES",
            )
        }
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.activity:activity-ktx:1.9.3")
    implementation("androidx.health.connect:connect-client:1.1.0")
    implementation("com.hivemq:hivemq-mqtt-client:1.3.3")

    testImplementation("junit:junit:4.13.2")
    testImplementation("org.json:json:20240303")
}
