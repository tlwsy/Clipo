import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.ktlint)
}
android {
    namespace = "app.clipo.android"
    compileSdk = 36
    defaultConfig {
        applicationId = "app.clipo.android"
        minSdk = 29
        targetSdk = 36
        versionCode = 2
        versionName = "0.1.0-m1"
    }
    buildFeatures { compose = true }
    sourceSets["main"].assets.srcDir("../fonts")
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}
kotlin { compilerOptions { jvmTarget.set(JvmTarget.JVM_17) } }
dependencies {
    implementation(project(":shared"))
    implementation(platform(libs.compose.bom))
    implementation(libs.compose.ui)
    implementation(libs.compose.foundation)
    implementation(libs.compose.material3)
    implementation(libs.activity)
    implementation(libs.lifecycle)
    implementation(libs.viewmodel)
    implementation(libs.coil.compose)
    implementation(libs.coil.network)
    implementation(libs.compose.icons)
}
