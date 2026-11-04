import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    alias(libs.plugins.kotlin.multiplatform)
    alias(libs.plugins.kotlin.serialization)
    alias(libs.plugins.android.library)
    alias(libs.plugins.sqldelight)
    alias(libs.plugins.ktlint)
}

kotlin {
    androidTarget { compilerOptions { jvmTarget.set(JvmTarget.JVM_17) } }
    jvm { compilerOptions { jvmTarget.set(JvmTarget.JVM_17) } }
    iosArm64()
    iosSimulatorArm64()
    targets.withType<org.jetbrains.kotlin.gradle.plugin.mpp.KotlinNativeTarget>().configureEach {
        binaries.framework {
            baseName = "ClipoShared"
            isStatic = true
        }
    }
    sourceSets {
        commonMain.dependencies {
            implementation(libs.ktor.core)
            implementation(libs.ktor.json)
            implementation(libs.ktor.serialization)
            implementation(libs.serialization)
            implementation(libs.coroutines)
            implementation(libs.sql.runtime)
            implementation(libs.sql.coroutines)
        }
        commonTest.dependencies {
            implementation(kotlin("test"))
            implementation(libs.ktor.mock)
            implementation(libs.coroutines.test)
        }
        androidMain.dependencies {
            implementation(libs.ktor.okhttp)
            implementation(libs.sql.android)
        }
        iosMain.dependencies {
            implementation(libs.ktor.darwin)
            implementation(libs.sql.native)
        }
        jvmMain.dependencies {
            implementation(libs.ktor.okhttp)
            implementation(libs.sql.jvm)
        }
    }
}
android {
    namespace = "app.clipo.shared"
    compileSdk = 36
    defaultConfig { minSdk = 29 }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}
sqldelight {
    databases {
        create("ClipoDatabase") {
            packageName.set("app.clipo.shared.db")
            schemaOutputDirectory.set(
                layout.buildDirectory
                    .dir("schema")
                    .get()
                    .asFile,
            )
            verifyMigrations.set(true)
        }
    }
}
ktlint {
    filter { exclude { it.file.path.contains("/generated/") } }
}
// SQLDelight attaches generated Kotlin after source-set filtering; lint only our common sources.
tasks.withType<org.jlleitschuh.gradle.ktlint.tasks.BaseKtLintCheckTask>().configureEach {
    if (name.endsWith("CommonMainSourceSet")) {
        setSource(fileTree("src/commonMain/kotlin") { exclude("**/generated/**") })
    }
}

val jvmTarget = kotlin.targets.getByName<org.jetbrains.kotlin.gradle.targets.jvm.KotlinJvmTarget>("jvm")
val jvmTests = jvmTarget.compilations.getByName("test")
tasks.register<JavaExec>("backendSmoke") {
    dependsOn("jvmTestClasses")
    classpath = jvmTests.output.allOutputs + jvmTests.runtimeDependencyFiles
    mainClass.set("app.clipo.shared.BackendSmokeKt")
}
