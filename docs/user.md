## 一、SDK依赖包清单
```groovy
// 统一管理版本
mavenBom "cn.crowddigital.usercenter:usercenter-dependencies:2.0.1-SNAPSHOT"

// 核心包，实现了与用户中心oauth2.0接口对接的核心业务逻辑，必须使用
implementation 'cn.crowddigital.usercenter:user-center-oauth2-personal-user-core'
// http接口包，简单提供了用户登录、登出相关的接口，非必须，可以自己实现相关的接口
implementation 'cn.crowddigital.usercenter:user-center-oauth2-personal-user-endpoint'
// 用户token信息保存redis实现，从用户中心获取到accessToken后，这个包会把信息保存到redis，非必须，可以自己实现其他方式的保存
implementation 'cn.crowddigital.usercenter:user-center-oauth2-personal-user-provider-redis'
```

## 二、Quick Start
1. 相关配置

logout-uri-config退出登录的地址规则参考：[https://crowddigital.yuque.com/wvaoo1/ov0uzh/uyr5yk](https://crowddigital.yuque.com/wvaoo1/ov0uzh/uyr5yk)

如：[https://dev.zhongshu.tech/pbc/usercenter/auth/web/#/logout?redirectUri=http%3A%2F%2Flocalhost%3A8080&channel=xxx](https://dev.zhongshu.tech/pbc/usercenter/auth/web/#/logout?redirectUri=http%3A%2F%2Flocalhost%3A8080&channel=xxx)（redirectUri为业务前端地址，channel为业务对接的登录渠道）。

```yaml
# oauth2相关配置
security:
  oauth2:
    client:
      client-id: $smartcity # oauth2的client_id，通过用户中心管理后台分配
      client-secret: smart#2020 # oauth2的secret，通过用户中心管理后台分配
      scope: basic # scope根据情况配置

oauth2:
  auth-server:
    base-uri: https://zhangzhg.crowddigital.cn/pbc/usercenter # 授权服务器基础地址
  personal:
    # token授权地址
    authorize-uri: ${oauth2.auth-server.base-uri}/oauth/authorize # 登录授权地址
    access-token-uri: ${oauth2.auth-server.base-uri}/oauth/token # 获取用户accessToken地址
    client-id: ${security.oauth2.client.client-id}
    client-secret: ${security.oauth2.client.client-secret}
    scope: ${security.oauth2.client.scope}
    logout-uri-config: # 如果使用了http接口包，退出登录后返回给前端的跳转地址mapping，前端根据需要跳转对应的地址
      supv-plat-web: ${oauth2.auth-server.base-uri}/applications
      supv-plat-h5: ${oauth2.auth-server.base-uri}/applications
  access-token-redis-prefix: 'demo:user:accessToken:' # 如果使用了accessToken保存redis实现依赖包，这边可以配置redis的key前辍

service:
  user-center:
    url: ${oauth2.auth-server.base-uri} # 授权服务器地址
```

2. 引入用户中心统一的maven bom及相关依赖

```groovy
// 引入maven bom进行版本管理
mavenBom "cn.crowddigital.usercenter:usercenter-dependencies:2.0.1-SNAPSHOT"

// 引入依赖
implementation 'cn.crowddigital.usercenter:user-center-oauth2-personal-user-core'
```

3. 注入Oauth2Service并使用参考如下

```java
@RestController
@RequiredArgsConstructor
@Api(tags = "用户接口")
@Slf4j
public class UserCenterLoginController {

    final Oauth2Service oauth2Service;
    final OAuth2Properties oAuth2Properties;

    @PostMapping("/public/usercenter-authorize-url")
    @ApiOperation("获取授权地址")
    public Oauth2Dto.UsercenterAuthorizeUrlResp authorizeUrl(@RequestBody Oauth2Dto.UsercenterAuthorizeUrlReq req) {
        return oauth2Service.authorizeUrl(req);
    }

    @PostMapping("/public/login")
    @ApiOperation("登录")
    public UserInfoDto.UserDetails login(@RequestBody Oauth2Dto.LoginReq req) {
        UserInfoDto.UserDetails userDetail = oauth2Service.loginWithUserDetail(req);
        
        // 也可以使用oauth2Service.login(req)，只返回openId，没有其他信息
        return userDetail;
    }

    @PostMapping("/user/get")
    @ApiOperation("获取用户信息")
    public UserInfoDto.UserDetails getUserInfo(@RequestBody Oauth2Dto.GetUserInfoReq req) {
        return oauth2Service.getUserDetail(req);
    }

    @PostMapping("/public/logout")
    public Oauth2Dto.LogoutRes logout() {
        return Oauth2Dto.LogoutRes.newBuilder()
                .setLogoutUriConfig(oAuth2Properties.getLogoutUriConfig())
                .build();
    }
}
```

4. 用户accessToken数据维护（可选）

```groovy
// 引入redis实现依赖
// 这个实现是把用户的accessToken放到redis了
implementation 'cn.crowddigital.usercenter:user-center-oauth2-personal-user-provider-redis'
```

## 三、其他
### 使用http接口包（可选）
1. 引入依赖

```groovy
implementation 'cn.crowddigital.usercenter:user-center-oauth2-personal-user-endpoint'
```

2. http接口清单
+ /public/usercenter-authorize-url 获取跳转用户中心授权登录的地址
+ /public/login 使用code进行登录并返回用户的各项信息
+ /public/logout 退出登录并返回退出登录后重定向的mapping数据，前端根据需要进行重定向跳转
+ /user/get 获取用户信息，与用户登录返回的用户信息一致

### 登录过程事件通知（可选）
```groovy
@Component
@RequiredArgsConstructor
public class LoginSuccessListenter implements UserEventListener {
    private final BizUserService bizUserService;
    @Override
    public void onUserInfoGet(UserInfoDto.UserDetails userDetails) {
        // 比如可以实现本地用户信息更新
    }

    @Override
    public void onAccessTokenGet(AccessTokenRes accessTokenRes) {
        // 比如可以实现openId的一些操作
    }
}
```

### 自行实现AccessToken保存和提供（可选）
目前只提供了redis版本的accessToken保存依赖包，需要其他方式的可以自行扩展实现，比如保存到mysql

```java
// 自己实现Oauth2DataProvider类，override两个方法，实现accessToken的保存，比如保存到数据库
@Service
@RequiredArgsConstructor
public class Oauth2DataProviderImpl implements Oauth2DataProvider {

    @Override
    public void saveUserAccessTokenRes(AccessTokenRes accessTokenRes, String openId) {
    }

    @Override
    public AccessTokenRes getUserAccessTokenRes(String openId) {
        // ......
    }
}
```

## 